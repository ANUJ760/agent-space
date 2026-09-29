"""Tests for M26 — NATS / JetStream integration.

Validates:
- NATS client publish & subscribe
- OutboxPublisherRelay dispatching events from PostgreSQL outbox to NATS
- Consumer idempotency: duplicate delivery of same message ID is executed only once
- Connection and reconnection lifecycle
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from app.config import Settings
from app.database import DatabaseManager
from app.nats import IdempotentConsumer, NatsClient, NatsMessage, OutboxPublisherRelay
from app.repositories.outbox_repo import OutboxRepository


class MockEventConsumer(IdempotentConsumer):
    """Test implementation of IdempotentConsumer."""

    def __init__(self, nats_client: NatsClient):
        super().__init__("mock_event_consumer", nats_client)
        self.received_events: list[dict[str, Any]] = []

    async def handle_event(self, event: dict[str, Any], msg_id: str) -> None:
        self.received_events.append(event)


@pytest.fixture()
async def nats_client() -> AsyncIterator[NatsClient]:
    """Create in-memory NATS client for deterministic testing."""
    client = NatsClient(url="memory://test-nats")
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()


@pytest.fixture()
async def db_manager(tmp_path: Path) -> AsyncIterator[DatabaseManager]:
    """Create an isolated test database manager."""
    db_path = tmp_path / "nats_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    settings = Settings(
        environment="test",
        debug=True,
        log_format="text",
        database_url=db_url,
    )
    db = DatabaseManager(settings.database)
    await db.connect()
    await db.create_all()
    try:
        yield db
    finally:
        await db.disconnect()


class TestNatsBasics:
    async def test_publish_and_subscribe(self, nats_client: NatsClient) -> None:
        received = []

        async def handler(msg: NatsMessage) -> None:
            received.append(msg)

        assert nats_client._in_memory is not None
        nats_client._in_memory.subscribe("agent_space.task.created", handler)

        payload = {"task_id": "123", "status": "TODO"}
        success = await nats_client.publish("agent_space.task.created", payload)
        assert success is True

        import asyncio

        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0].subject == "agent_space.task.created"

    async def test_connection_lifecycle(self, nats_client: NatsClient) -> None:
        assert nats_client.is_connected is True
        await nats_client.disconnect()
        assert nats_client.is_connected is False


class TestIdempotentConsumer:
    async def test_duplicate_delivery_is_processed_only_once(self, nats_client: NatsClient) -> None:
        consumer = MockEventConsumer(nats_client)
        msg_id = "msg-unique-12345"

        msg1 = NatsMessage(
            subject="events.task",
            data=b'{"action": "task_assigned", "agent_id": "agent-1"}',
            msg_id=msg_id,
        )
        msg2 = NatsMessage(
            subject="events.task",
            data=b'{"action": "task_assigned", "agent_id": "agent-1"}',
            msg_id=msg_id,
        )

        # First delivery — must be processed
        processed1 = await consumer.process_raw_message(msg1)
        assert processed1 is True
        assert consumer.processed_count == 1
        assert consumer.duplicate_count == 0
        assert len(consumer.received_events) == 1
        assert msg1.is_acked is True

        # Second delivery with identical msg_id — must be detected as duplicate and skipped
        processed2 = await consumer.process_raw_message(msg2)
        assert processed2 is False
        assert consumer.processed_count == 1
        assert consumer.duplicate_count == 1
        assert len(consumer.received_events) == 1  # Unchanged!
        assert msg2.is_acked is True  # Acked so queue doesn't re-deliver forever


class TestOutboxPublisherRelay:
    async def test_relay_unprocessed_outbox_events(
        self,
        db_manager: DatabaseManager,
        nats_client: NatsClient,
    ) -> None:
        from app.models.organization import Organization
        from app.models.project import Project

        relay = OutboxPublisherRelay(nats_client)
        task_id = uuid.uuid4()

        # Step 1: Create org & project, then write event to Outbox table
        async with db_manager.session_factory() as session:
            org = Organization(name="Relay Org", slug="relay-org")
            session.add(org)
            await session.flush()

            proj = Project(
                organization_id=org.id,
                name="Relay Project",
                slug="relay-project",
            )
            session.add(proj)
            await session.flush()

            repo = OutboxRepository(session)
            event = await repo.record_event(
                event_type="task.created",
                aggregate_type="task",
                aggregate_id=task_id,
                payload={"title": "Test task", "priority": "HIGH"},
                project_id=proj.id,
                organization_id=org.id,
            )
            event_id = event.id
            await session.commit()

        # Step 2: Run Outbox relay
        async with db_manager.session_factory() as session:
            count = await relay.relay_batch(session, batch_size=10)
            assert count == 1
            await session.commit()

        # Step 3: Verify the event is now marked published in DB
        async with db_manager.session_factory() as session:
            repo = OutboxRepository(session)
            pending = await repo.list_pending()
            assert not any(e.id == event_id for e in pending)

            # Relaying again should do 0
            count2 = await relay.relay_batch(session, batch_size=10)
            assert count2 == 0
