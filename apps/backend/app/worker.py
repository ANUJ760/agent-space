"""Production worker: transactional outbox relay, NATS dispatcher, Temporal activities."""

from __future__ import annotations

import asyncio
import json
import signal
import uuid
from contextlib import suppress

import structlog
from nats.errors import TimeoutError as NatsTimeoutError
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from app.config import get_settings
from app.database import DatabaseManager, set_db_manager
from app.models.agent import Agent
from app.nats import NatsClient, OutboxPublisherRelay
from app.temporal.activities.default_agent import (
    execute_default_agent_task,
    fail_default_agent_task,
)
from app.temporal.client import TemporalService
from app.temporal.workflows.default_agent_workflow import DefaultAgentTaskWorkflow

logger = structlog.stdlib.get_logger(__name__)


async def relay_outbox(db: DatabaseManager, relay: OutboxPublisherRelay, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async with db.session_factory() as session:
                count = await relay.relay_batch(session)
                await session.commit()
            if count:
                logger.info("outbox_batch_published", count=count)
        except Exception:
            logger.exception("outbox_relay_failed")
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(0.25 if count else 1)


async def dispatch_assignments(db: DatabaseManager, nats: NatsClient, temporal: TemporalService, stop: asyncio.Event) -> None:
    subscription = await nats.jetstream.pull_subscribe(
        "agent_space.events.task.assigned",
        durable="default-agent-dispatch",
        stream=nats.stream_name,
    )
    while not stop.is_set():
        try:
            messages = await subscription.fetch(batch=10, timeout=1)
        except NatsTimeoutError:
            continue
        for message in messages:
            try:
                event = json.loads(message.data)
                payload = event.get("payload", {})
                if payload.get("assignee_type") != "AGENT":
                    await message.ack()
                    continue
                agent_id = uuid.UUID(payload["assignee_id"])
                async with db.session_factory() as session:
                    agent = await session.get(Agent, agent_id)
                if agent is None or agent.model_provider != "default":
                    # User-key agents execute only in the assigning browser.
                    await message.ack()
                    continue
                workflow_id = f"default-agent-{event['id']}"
                with suppress(WorkflowAlreadyStartedError):
                    await temporal.start_workflow(
                        "DefaultAgentTaskWorkflow",
                        workflow_id,
                        {"task_id": payload["task_id"], "agent_id": str(agent_id)},
                    )
                await message.ack()
            except Exception:
                logger.exception("assignment_dispatch_failed")
                await message.nak(delay=5)


async def main() -> None:
    settings = get_settings()
    db = DatabaseManager(settings.database)
    await db.connect()
    set_db_manager(db)
    nats = NatsClient(
        url=settings.nats_url,
        auth_token=settings.nats_auth_token.get_secret_value() if settings.nats_auth_token else None,
        stream_name=settings.nats_stream_name,
    )
    temporal = TemporalService(
        host=settings.temporal_host,
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
        api_key=settings.temporal_api_key.get_secret_value() if settings.temporal_api_key else None,
        tls=settings.temporal_tls,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    try:
        await nats.connect()
        await nats.ensure_stream()
        await temporal.connect()
        worker = Worker(
            temporal.client,
            task_queue=settings.temporal_task_queue,
            workflows=[DefaultAgentTaskWorkflow],
            activities=[execute_default_agent_task, fail_default_agent_task],
        )
        tasks = [
            asyncio.create_task(relay_outbox(db, OutboxPublisherRelay(nats), stop)),
            asyncio.create_task(dispatch_assignments(db, nats, temporal, stop)),
            asyncio.create_task(worker.run()),
        ]
        stop_task = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*tasks, stop_task], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is stop_task:
                continue
            error = task.exception()
            if error is not None:
                raise error
            raise RuntimeError("Worker component stopped unexpectedly")
    finally:
        stop.set()
        if "stop_task" in locals():
            stop_task.cancel()
        for task in locals().get("tasks", []):
            task.cancel()
        if "tasks" in locals():
            await asyncio.gather(*tasks, return_exceptions=True)
        await temporal.disconnect()
        await nats.disconnect()
        await db.disconnect()
        set_db_manager(None)


if __name__ == "__main__":
    asyncio.run(main())
