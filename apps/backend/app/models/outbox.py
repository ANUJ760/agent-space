"""Transactional outbox model for reliable domain event publishing."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OutboxEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only domain event stored in the same transaction as state mutations."""

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=False,
        default=dict,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
