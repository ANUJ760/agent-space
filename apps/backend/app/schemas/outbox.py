"""Pydantic schemas for audit outbox events."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OutboxEventResponse(BaseModel):
    """Schema representing an audit outbox event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    payload: dict[str, Any]
    published_at: datetime | None = None
    created_at: datetime
