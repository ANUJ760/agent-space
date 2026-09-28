"""Organization Pydantic schemas for API requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """Payload to create a new organization."""

    name: str = Field(min_length=2, max_length=255, description="Organization display name")
    slug: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description="URL-friendly slug (lowercase letters, numbers, hyphens)",
    )
    description: str | None = Field(default=None, max_length=1024)


class OrganizationUpdate(BaseModel):
    """Payload to update an organization."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    is_active: bool | None = None


class OrganizationResponse(BaseModel):
    """Public representation of an Organization."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}
