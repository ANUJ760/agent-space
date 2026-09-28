"""Pydantic schemas for Agent Registry operations."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    """Payload to register a new agent."""

    name: str = Field(min_length=1, max_length=255, description="Human-readable agent name")
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe unique identifier within organization",
    )
    description: str | None = Field(default=None, max_length=2048)
    role: str = Field(
        default="DEVELOPER",
        max_length=50,
        description="Specialized role (e.g. ARCHITECT, DEVELOPER, TESTER, REVIEWER)",
    )
    model: str = Field(
        default="claude-3-5-sonnet",
        max_length=100,
        description="Underlying foundation model identifier",
    )
    model_provider: str = Field(
        default="anthropic",
        max_length=50,
        description="Provider name (anthropic, openai, google, ollama)",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of capabilities (e.g. code_writing, git_ops, testing)",
    )
    system_prompt: str | None = Field(
        default=None,
        max_length=8192,
        description="Custom system prompt instructions",
    )
    status: str = Field(
        default="ACTIVE",
        max_length=50,
        description="Lifecycle status (ACTIVE, INACTIVE, DEPRECATED)",
    )
    configuration: dict[str, Any] = Field(
        default_factory=dict,
        description="Model parameters and tool configurations",
    )
    project_id: uuid.UUID | None = Field(
        default=None,
        description="Optional project scope (null for organization-wide agent)",
    )


class AgentUpdate(BaseModel):
    """Payload to update an existing agent definition."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    role: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=100)
    model_provider: str | None = Field(default=None, max_length=50)
    capabilities: list[str] | None = None
    system_prompt: str | None = Field(default=None, max_length=8192)
    status: str | None = Field(default=None, max_length=50)
    configuration: dict[str, Any] | None = None


class AgentResponse(BaseModel):
    """Serialized Agent representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    slug: str
    description: str | None
    role: str
    model: str
    model_provider: str
    capabilities: list[str]
    system_prompt: str | None
    status: str
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int
