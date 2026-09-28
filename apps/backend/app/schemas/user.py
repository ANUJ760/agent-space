"""User Pydantic schemas for API requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.organization import OrganizationResponse


class UserResponse(BaseModel):
    """Public representation of a User."""

    id: uuid.UUID
    external_subject: str
    email: str
    username: str
    display_name: str | None = None
    role: str
    is_active: bool
    organization_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    """Detailed profile representation for GET /api/v1/auth/me."""

    id: uuid.UUID
    external_subject: str
    email: str
    username: str
    display_name: str | None = None
    role: str
    is_active: bool
    organization: OrganizationResponse | None = None
    token_roles: list[str] = []

    model_config = {"from_attributes": True}
