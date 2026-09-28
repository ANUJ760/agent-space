"""Task SQLAlchemy ORM model for units of work executed by agents and humans."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.user import User


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """A unit of computational or engineering work assigned to an agent or user."""

    __tablename__ = "tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(4096), nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="TODO", index=True)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default="MEDIUM", index=True)

    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    context: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=False,
        default=dict,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    project: Mapped["Project"] = relationship("Project")
    assigned_agent: Mapped["Agent | None"] = relationship("Agent")
    assigned_user: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_user_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
