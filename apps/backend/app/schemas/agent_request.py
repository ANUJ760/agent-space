"""Pydantic schemas for Agent to Human requests and Human responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRequestType(StrEnum):
    """Supported agent-to-human request categories."""

    APPROVAL = "APPROVAL"
    DECISION = "DECISION"
    HELP = "HELP"
    TAKEOVER = "TAKEOVER"


class AgentHumanRequestCreate(BaseModel):
    """Payload created by an agent when it needs durable human intervention."""

    request_type: AgentRequestType
    prompt: str = Field(min_length=1, max_length=4096, description="Question or approval prompt")
    options: list[str] = Field(
        default_factory=list, description="Candidate choices for DECISION or APPROVAL"
    )
    context: dict[str, Any] = Field(
        default_factory=dict, description="Execution context or diff snippet"
    )


class HumanResponsePayload(BaseModel):
    """Payload provided by a human user to resolve a pending agent request."""

    action: str = Field(description="Action taken, e.g. APPROVE, REJECT, CHOSEN, ANSWER")
    feedback: str | None = Field(
        default=None, max_length=4096, description="Human feedback or guidance"
    )
    selected_option: str | None = Field(default=None, description="Selected option if applicable")


class AgentHumanRequestResponse(BaseModel):
    """Serialized representation of an agent's request to human."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    request_type: str
    prompt: str
    options: list[str]
    status: str  # PENDING, RESOLVED, CANCELLED
    context: dict[str, Any]
    response: dict[str, Any] | None = None
    created_at: datetime
    resolved_at: datetime | None = None
