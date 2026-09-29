"""Project progress calculation service based on configurable task status weights."""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas.progress import DEFAULT_PROGRESS_WEIGHTS, ProjectProgressResponse


class ProjectProgressCalculator:
    """Calculates weighted completion percentages from task states."""

    def __init__(self, custom_weights: dict[str, float] | None = None) -> None:
        self.weights = dict(DEFAULT_PROGRESS_WEIGHTS)
        if custom_weights:
            self.weights.update(custom_weights)

    def calculate(
        self,
        project_id: uuid.UUID,
        tasks: list[Any],
        agent_activity_count: int = 0,
    ) -> ProjectProgressResponse:
        """Calculate weighted progress across all tasks in a project."""
        total = len(tasks)
        if total == 0:
            return ProjectProgressResponse(
                project_id=project_id,
                total_progress_pct=0.0,
                total_tasks=0,
                completed_tasks=0,
                active_tasks=0,
                blocked_tasks=0,
                todo_tasks=0,
                agent_activity_count=agent_activity_count,
                weights_applied=self.weights,
            )

        completed = 0
        active = 0
        blocked = 0
        todo = 0
        total_weighted_score = 0.0

        for t in tasks:
            status = getattr(t, "status", None) or "TODO"
            weight = self.weights.get(status, 0.0)
            total_weighted_score += weight

            if status == "DONE":
                completed += 1
            elif status in ("CLAIMED", "IN_PROGRESS", "REVIEW"):
                active += 1
            elif status in ("BLOCKED", "FAILED"):
                blocked += 1
            elif status == "TODO":
                todo += 1

        pct = round((total_weighted_score / total) * 100.0, 1)

        return ProjectProgressResponse(
            project_id=project_id,
            total_progress_pct=min(100.0, max(0.0, pct)),
            total_tasks=total,
            completed_tasks=completed,
            active_tasks=active,
            blocked_tasks=blocked,
            todo_tasks=todo,
            agent_activity_count=agent_activity_count,
            weights_applied=self.weights,
        )
