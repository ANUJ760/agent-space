"""Pydantic schemas for TaskDependency DAG operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskDependencyCreate(BaseModel):
    """Payload to add a prerequisite dependency to a task."""

    depends_on_task_id: uuid.UUID = Field(
        description="UUID of the prerequisite task that must be completed first."
    )


class TaskDependencyResponse(BaseModel):
    """Representation of an established task dependency edge."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID
    created_at: datetime


class TaskDependencyItemResponse(BaseModel):
    """Prerequisite task item details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    priority: str
