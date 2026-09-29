"""Pydantic schemas for Agent Activity Feed."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivityFeedItem(BaseModel):
    """Safe, sanitized agent activity event item.

    Guarantees: Zero chain-of-thought or raw internal reasoning exposure.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    agent_name: str
    agent_role: str
    action: str
    summary: str = Field(description="Safe, sanitized one-line summary of agent activity")
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
