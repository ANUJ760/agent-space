"""ProjectMember Pydantic schemas for API requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectMemberCreate(BaseModel):
    """Payload to assign a user to a project with a role."""

    user_id: uuid.UUID = Field(description="UUID of the internal user to assign")
    role: str = Field(
        default="MEMBER",
        pattern=r"^(PROJECT_OWNER|PROJECT_ADMIN|MEMBER|VIEWER)$",
        description="Assigned project role",
    )


class ProjectMemberUpdate(BaseModel):
    """Payload to update a member's project role."""

    role: str = Field(
        pattern=r"^(PROJECT_OWNER|PROJECT_ADMIN|MEMBER|VIEWER)$",
        description="Updated project role",
    )


class ProjectMemberResponse(BaseModel):
    """Public representation of a project membership."""

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    username: str | None = None
    email: str | None = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}
