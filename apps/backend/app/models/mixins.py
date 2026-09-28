"""Common model mixins and column patterns.

Provides reusable mixins for standard columns like timestamps,
UUIDs, and optimistic versioning that will be used across all
domain models.
"""

import uuid as uuid_mod
from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds created_at and updated_at columns with server-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key column named ``id``."""

    id: Mapped[uuid_mod.UUID] = mapped_column(
        primary_key=True,
        default=uuid_mod.uuid4,
    )


class VersionMixin:
    """Adds an integer ``version`` column for optimistic concurrency control.

    Every update must increment the version and include the expected
    version in the WHERE clause. If no row is updated, the caller
    must raise a version conflict error.
    """

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
