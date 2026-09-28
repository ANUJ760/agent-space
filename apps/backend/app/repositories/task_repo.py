"""Repository for Task database operations."""

import uuid

from sqlalchemy import func, select

from app.models.task import Task
from app.repositories import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Data access repository for Task entities."""

    model_class = Task

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
        status: str | None = None,
        priority: str | None = None,
        assigned_agent_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
    ) -> list[Task]:
        """List tasks within a project with optional filters."""
        stmt = (
            select(Task)
            .where(Task.project_id == project_id)
            .offset(offset)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
        if assigned_agent_id:
            stmt = stmt.where(Task.assigned_agent_id == assigned_agent_id)
        if assigned_user_id:
            stmt = stmt.where(Task.assigned_user_id == assigned_user_id)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(self, project_id: uuid.UUID, status: str | None = None) -> int:
        """Count total tasks in a project, optionally filtered by status."""
        stmt = select(func.count(Task.id)).where(Task.project_id == project_id)
        if status:
            stmt = stmt.where(Task.status == status)
        result = await self._session.execute(stmt)
        return result.scalar() or 0
