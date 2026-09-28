"""Idempotency record ORM model for duplicate mutation prevention."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Stores request hashes and cached responses for idempotent operations."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), nullable=False)
    request_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PROCESSING", index=True
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict[str, str]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=False,
        default=dict,
    )
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
