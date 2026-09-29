"""NATS JetStream event messaging and outbox publisher relay for Agent Space.

Flow:
    PostgreSQL outbox (authoritative)
             ↓
    OutboxPublisherRelay
             ↓
    NATS JetStream (deduplicated by msg_id)
             ↓
    Idempotent Event Consumers
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


class NatsMessage:
    """Lightweight abstraction for a JetStream or in-memory message."""

    def __init__(self, subject: str, data: bytes, msg_id: str | None = None, headers: dict[str, str] | None = None):
        self.subject = subject
        self.data = data
        self.msg_id = msg_id or (headers.get("Nats-Msg-Id") if headers else str(uuid.uuid4()))
        self.headers = headers or {}
        self._acked = False

    async def ack(self) -> None:
        self._acked = True

    @property
    def is_acked(self) -> bool:
        return self._acked


class InMemoryNatsTransport:
    """Asyncio-safe in-memory NATS JetStream transport for testing without external broker."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[Callable[[NatsMessage], Coroutine[Any, Any, None]]]] = {}
        self._published_messages: list[NatsMessage] = []
        self._dedup_keys: set[str] = set()
        self._lock = asyncio.Lock()
        self.is_connected = True

    async def publish(self, subject: str, data: bytes, msg_id: str | None = None) -> bool:
        async with self._lock:
            if not self.is_connected:
                raise ConnectionError("NATS transport disconnected")
            if msg_id and msg_id in self._dedup_keys:
                logger.debug("nats_inmemory_duplicate_ignored", msg_id=msg_id)
                return False
            if msg_id:
                self._dedup_keys.add(msg_id)

            msg = NatsMessage(subject=subject, data=data, msg_id=msg_id)
            self._published_messages.append(msg)

            # Route to matching subscribers
            for sub_subject, handlers in self._subscriptions.items():
                if sub_subject == subject or sub_subject == ">" or sub_subject.endswith(".>"):
                    for handler in handlers:
                        asyncio.create_task(handler(msg))
            return True

    def subscribe(self, subject: str, handler: Callable[[NatsMessage], Coroutine[Any, Any, None]]) -> None:
        if subject not in self._subscriptions:
            self._subscriptions[subject] = []
        self._subscriptions[subject].append(handler)


class NatsClient:
    """NATS client and JetStream manager."""

    def __init__(
        self,
        url: str = "nats://localhost:4222",
        stream_name: str = "AGENT_SPACE_EVENTS",
        subjects: list[str] | None = None,
    ):
        self.url = url
        self.stream_name = stream_name
        self.subjects = subjects or ["agent_space.>"]
        self._nc: Any = None
        self._js: Any = None
        self._in_memory: InMemoryNatsTransport | None = None
        self._is_in_memory = url.startswith("memory://")

    async def connect(self) -> None:
        """Connect to NATS broker and initialize JetStream context."""
        if self._is_in_memory:
            self._in_memory = InMemoryNatsTransport()
            logger.info("nats_connected_in_memory")
            return

        import nats

        async def error_cb(e: Exception) -> None:
            logger.warning("nats_error_callback", error=str(e))

        async def reconnected_cb() -> None:
            logger.info("nats_reconnected_callback")

        async def closed_cb() -> None:
            logger.info("nats_connection_closed_callback")

        self._nc = await nats.connect(
            self.url,
            error_cb=error_cb,
            reconnected_cb=reconnected_cb,
            closed_cb=closed_cb,
            connect_timeout=5,
        )
        self._js = self._nc.jetstream()
        logger.info("nats_connected", url=self.url)

    async def disconnect(self) -> None:
        """Gracefully drain and close NATS connection."""
        if self._nc is not None:
            await self._nc.drain()
            await self._nc.close()
            self._nc = None
            self._js = None
        if self._in_memory is not None:
            self._in_memory.is_connected = False
            self._in_memory = None
        logger.info("nats_disconnected")

    @property
    def is_connected(self) -> bool:
        if self._is_in_memory and self._in_memory:
            return self._in_memory.is_connected
        return self._nc is not None and self._nc.is_connected

    async def ensure_stream(self) -> None:
        """Create or update JetStream stream configuration."""
        if self._is_in_memory:
            return

        if self._js is None:
            await self.connect()

        try:
            from nats.js.api import RetentionPolicy, StorageType, StreamConfig

            config = StreamConfig(
                name=self.stream_name,
                subjects=self.subjects,
                storage=StorageType.FILE,
                retention=RetentionPolicy.LIMITS,
                duplicate_window=120,  # 2 minute deduplication window
            )
            await self._js.add_stream(config)
            logger.info("jetstream_stream_ensured", stream=self.stream_name)
        except Exception as exc:
            # Stream might already exist
            logger.debug("jetstream_add_stream_info", error=str(exc))

    async def publish(
        self,
        subject: str,
        payload: dict[str, Any],
        msg_id: str | None = None,
    ) -> bool:
        """Publish JSON payload to JetStream with deduplication msg_id."""
        data = json.dumps(payload).encode("utf-8")
        if self._is_in_memory and self._in_memory:
            return await self._in_memory.publish(subject, data, msg_id=msg_id)

        if self._js is None:
            await self.connect()

        headers = {"Nats-Msg-Id": msg_id} if msg_id else {}
        ack = await self._js.publish(subject, data, headers=headers)
        return ack is not None


class IdempotentConsumer:
    """Base class for JetStream event consumers with guaranteed deduplication."""

    def __init__(self, consumer_name: str, nats_client: NatsClient):
        self.consumer_name = consumer_name
        self.nats_client = nats_client
        self._processed_msg_ids: set[str] = set()
        self.processed_count: int = 0
        self.duplicate_count: int = 0

    async def process_raw_message(self, msg: Any) -> bool:
        """Process incoming raw message, ensuring strict idempotency."""
        msg_id: str = getattr(msg, "msg_id", None) or (
            msg.headers.get("Nats-Msg-Id") if getattr(msg, "headers", None) else None
        ) or str(uuid.uuid4())

        # Check for duplicate delivery
        if msg_id in self._processed_msg_ids:
            self.duplicate_count += 1
            logger.info(
                "consumer_duplicate_delivery_skipped",
                consumer=self.consumer_name,
                msg_id=msg_id,
            )
            if hasattr(msg, "ack"):
                await msg.ack()
            return False

        # Parse event payload
        try:
            raw_data = msg.data.decode("utf-8") if isinstance(msg.data, (bytes, bytearray)) else msg.data
            payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception as exc:
            logger.error("consumer_payload_parse_error", consumer=self.consumer_name, error=str(exc))
            if hasattr(msg, "ack"):
                await msg.ack()
            return False

        # Execute subclass domain logic
        await self.handle_event(payload, msg_id=msg_id)

        # Mark processed and acknowledge
        self._processed_msg_ids.add(msg_id)
        self.processed_count += 1
        if hasattr(msg, "ack"):
            await msg.ack()
        return True

    async def handle_event(self, event: dict[str, Any], msg_id: str) -> None:
        """Domain handler method to be overridden by specific consumers."""
        raise NotImplementedError


class OutboxPublisherRelay:
    """Relays pending PostgreSQL outbox events to NATS JetStream and marks them published."""

    def __init__(self, nats_client: NatsClient, subject_prefix: str = "agent_space.events"):
        self.nats_client = nats_client
        self.subject_prefix = subject_prefix

    async def relay_batch(self, session: Any, batch_size: int = 50) -> int:
        """Fetch unpublished outbox events and publish each to JetStream.

        Returns the number of events published.
        """
        from app.repositories.outbox_repo import OutboxRepository

        repo = OutboxRepository(session)
        pending = await repo.list_pending(limit=batch_size)
        if not pending:
            return 0

        dispatched = 0
        for event in pending:
            subject = f"{self.subject_prefix}.{event.event_type}"
            payload = {
                "id": str(event.id),
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "organization_id": str(event.organization_id) if event.organization_id else None,
                "project_id": str(event.project_id) if event.project_id else None,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "payload": event.payload,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }

            # Outbox event ID is the JetStream deduplication key
            msg_id = str(event.id)
            published = await self.nats_client.publish(subject, payload, msg_id=msg_id)
            if published:
                await repo.mark_published(event.id)
                dispatched += 1

        return dispatched
