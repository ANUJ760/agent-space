"""Project Pydantic schemas for API requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Payload to create a new project."""

    name: str = Field(min_length=2, max_length=255, description="Project display name")
    slug: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description="URL-friendly slug (lowercase letters, numbers, hyphens)",
    )
    description: str | None = Field(default=None, max_length=2048)
    repository_url: str | None = Field(default=None, max_length=1024)
    default_branch: str = Field(default="main", max_length=100)


class ProjectUpdate(BaseModel):
    """Payload to update an existing project."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    status: str | None = Field(default=None, max_length=50)
    repository_url: str | None = Field(default=None, max_length=1024)
    default_branch: str | None = Field(default=None, max_length=100)


class ProjectResponse(BaseModel):
    """Public representation of a Project."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    status: str
    repository_url: str | None = None
    default_branch: str
    created_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}


class ProjectSummaryResponse(BaseModel):
    """Executive summary metrics for a project."""

    project: ProjectResponse
    member_count: int = 0
    task_count: int = 0
    agent_count: int = 0
    status: str
