"""Test model for verifying database infrastructure and mixins."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class TestModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """Minimal model for database connectivity and CRUD verification."""

    __test__ = False
    __tablename__ = "test_items"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
