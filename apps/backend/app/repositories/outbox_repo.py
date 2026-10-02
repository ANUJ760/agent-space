"""Repository for transactional OutboxEvent persistence and retrieval."""

import uuid
from typing import Any

from sqlalchemy import func, select, update

from app.models.outbox import OutboxEvent
from app.repositories import BaseRepository


class OutboxRepository(BaseRepository[OutboxEvent]):
    """Data access layer for domain outbox events."""

    async def record_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: dict[str, Any],
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> OutboxEvent:
        """Create and add a new outbox event to the current transaction."""
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[OutboxEvent]:
        """List audit outbox events for a project ordered chronologically."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.project_id == project_id)
            .order_by(OutboxEvent.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """Fetch unpublished outbox events for background relay."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
        if self._session.bind and self._session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_published(self, event_id: uuid.UUID) -> None:
        """Mark an outbox event as successfully dispatched."""
        stmt = update(OutboxEvent).where(OutboxEvent.id == event_id).values(published_at=func.now())
        await self._session.execute(stmt)
        await self._session.flush()
