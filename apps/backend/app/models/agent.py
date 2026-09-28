"""Agent SQLAlchemy ORM model for autonomous workers and assistants."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.project import Project


class Agent(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """Registered autonomous AI agent definition and capabilities."""

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_agents_org_slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional project scoping: None indicates an organization-wide agent
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    role: Mapped[str] = mapped_column(String(50), nullable=False, default="DEVELOPER", index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="claude-3-5-sonnet")
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")

    capabilities: Mapped[list[str]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=False,
        default=list,
    )
    system_prompt: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE", index=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=False,
        default=dict,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    project: Mapped["Project | None"] = relationship("Project")
