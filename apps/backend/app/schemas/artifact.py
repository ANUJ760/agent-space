"""Artifact request and response Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArtifactBase(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    artifact_type: str = "OTHER"  # CODE, IMAGE, DOCUMENT, LOGS, TEST_RESULTS, DIFF, OTHER
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ArtifactCreate(ArtifactBase):
    task_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    storage_key: str
    size_bytes: int
    sha256_hash: str


class ArtifactResponse(ArtifactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    created_by_id: uuid.UUID | None = None
    storage_key: str
    size_bytes: int
    sha256_hash: str
    version: int
    created_at: datetime
    updated_at: datetime


class ArtifactPreviewResponse(BaseModel):
    artifact_id: uuid.UUID
    artifact_type: str
    filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    preview_content: str | dict[str, Any] | None = None
    is_truncated: bool = False
    presigned_url: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
