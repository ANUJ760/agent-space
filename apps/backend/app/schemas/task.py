"""Pydantic schemas for Task operations and state transitions."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskPriority(StrEnum):
    """Task urgency levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssigneeType(StrEnum):
    """Supported task worker assignment categories."""

    HUMAN = "HUMAN"
    AGENT = "AGENT"


class TaskAssignRequest(BaseModel):
    """Payload to assign a task to a user or agent."""

    assignee_type: AssigneeType = Field(description="Worker type: HUMAN or AGENT")
    assignee_id: uuid.UUID = Field(description="UUID of the User or Agent to assign")
    allow_takeover: bool = Field(
        default=False,
        description="Whether to forcefully take over an already-assigned task",
    )


class TaskCreate(BaseModel):
    """Payload to create a new task within a project."""

    title: str = Field(min_length=1, max_length=255, description="Brief task summary")
    description: str | None = Field(default=None, max_length=4096)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    assigned_agent_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured task input context, prompt params, or file references",
    )


class TaskUpdate(BaseModel):
    """Payload to update an existing task.

    If status is specified, it must satisfy valid state machine transitions.
    If expected_version is specified, enforces optimistic concurrency locking.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    priority: TaskPriority | None = None
    status: str | None = Field(
        default=None,
        description="Desired task lifecycle status (validated by state machine)",
    )
    assigned_agent_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    context: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = Field(default=None, max_length=2048)
    expected_version: int | None = Field(
        default=None,
        description="Expected version for optimistic concurrency control (blocks stale updates)",
    )


class TaskTransitionRequest(BaseModel):
    """Dedicated payload for explicit task state transitions."""

    status: str = Field(description="Target TaskStatus")
    reason: str | None = Field(
        default=None, max_length=1024, description="Optional transition reason"
    )
    expected_version: int | None = Field(
        default=None,
        description="Expected version for optimistic concurrency control",
    )


class TaskTakeoverRequest(BaseModel):
    """Payload for human takeover of a task from an agent."""

    reason: str | None = Field(default=None, max_length=1024, description="Reason for takeover")
    expected_version: int | None = Field(default=None, description="Optional expected version for optimistic CAS")


class TaskHandoffRequest(BaseModel):
    """Payload to hand off task from human to an agent."""

    agent_id: uuid.UUID = Field(description="UUID of the agent to resume task")
    instructions: str | None = Field(default=None, max_length=4096, description="Specific instructions for agent")
    expected_version: int | None = Field(default=None, description="Optional expected version for optimistic CAS")


class TaskResponse(BaseModel):
    """Serialized Task representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: str
    priority: str
    assigned_agent_id: uuid.UUID | None
    assigned_user_id: uuid.UUID | None
    created_by_id: uuid.UUID | None
    context: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    version: int
