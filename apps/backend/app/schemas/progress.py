"""Pydantic schemas for Project Progress calculation."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PROGRESS_WEIGHTS: dict[str, float] = {
    "TODO": 0.0,
    "CLAIMED": 0.10,
    "IN_PROGRESS": 0.50,
    "REVIEW": 0.90,
    "DONE": 1.0,
    "BLOCKED": 0.0,
    "FAILED": 0.0,
}


class ProjectProgressResponse(BaseModel):
    """Aggregated project progress metrics."""

    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    total_progress_pct: float = Field(
        ge=0.0, le=100.0, description="Overall project completion percentage"
    )
    total_tasks: int
    completed_tasks: int
    active_tasks: int
    blocked_tasks: int
    todo_tasks: int
    agent_activity_count: int = 0
    weights_applied: dict[str, float]
