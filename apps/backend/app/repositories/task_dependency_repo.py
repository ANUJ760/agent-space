"""Repository for TaskDependency operations and graph cycle detection."""

import uuid
from typing import Any

from sqlalchemy import delete, select

from app.errors import BadRequestError, ConflictError
from app.models.task import Task
from app.models.task_dependency import TaskDependency
from app.repositories import BaseRepository
from app.services.task_state_machine import TaskStatus


class TaskDependencyRepository(BaseRepository[TaskDependency]):
    """Data access repository for task DAG dependencies and cycle validation."""

    model_class = TaskDependency

    async def list_dependencies(self, task_id: uuid.UUID) -> list[Task]:
        """Return all prerequisite tasks that the given task_id depends upon."""
        stmt = (
            select(Task)
            .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
            .where(TaskDependency.task_id == task_id)
            .order_by(Task.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_dependents(self, task_id: uuid.UUID) -> list[Task]:
        """Return all downstream tasks that depend on the given task_id."""
        stmt = (
            select(Task)
            .join(TaskDependency, TaskDependency.task_id == Task.id)
            .where(TaskDependency.depends_on_task_id == task_id)
            .order_by(Task.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def would_create_cycle(self, task_id: uuid.UUID, depends_on_task_id: uuid.UUID) -> bool:
        """Check whether adding an edge task_id -> depends_on_task_id creates a directed cycle.

        A cycle occurs if task_id is already reachable from depends_on_task_id.
        """
        if task_id == depends_on_task_id:
            return True

        visited: set[uuid.UUID] = set()
        queue: list[uuid.UUID] = [depends_on_task_id]

        while queue:
            current = queue.pop(0)
            if current == task_id:
                return True

            if current in visited:
                continue
            visited.add(current)

            # Query all tasks that 'current' depends upon
            stmt = select(TaskDependency.depends_on_task_id).where(
                TaskDependency.task_id == current
            )
            result = await self._session.execute(stmt)
            for next_dep in result.scalars().all():
                if next_dep not in visited:
                    queue.append(next_dep)

        return False

    async def add_dependency(
        self, task_id: uuid.UUID, depends_on_task_id: uuid.UUID
    ) -> TaskDependency:
        """Add a directed dependency edge, enforcing cycle prevention and self-dependency rules."""
        if task_id == depends_on_task_id:
            raise BadRequestError(
                message="A task cannot depend on itself.",
                details={"task_id": str(task_id)},
            )

        # Check existing edge
        stmt = select(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.depends_on_task_id == depends_on_task_id,
        )
        result = await self._session.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            return existing

        # Cycle detection
        if await self.would_create_cycle(task_id, depends_on_task_id):
            raise ConflictError(
                code="CYCLIC_DEPENDENCY",
                message="Cannot add dependency: operation would introduce a cycle in the task graph.",
                details={
                    "task_id": str(task_id),
                    "depends_on_task_id": str(depends_on_task_id),
                },
            )

        dep = TaskDependency(
            task_id=task_id,
            depends_on_task_id=depends_on_task_id,
        )
        return await self.create(dep)

    async def remove_dependency(self, task_id: uuid.UUID, depends_on_task_id: uuid.UUID) -> bool:
        """Remove a dependency edge. Returns True if a record was deleted."""
        stmt = delete(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.depends_on_task_id == depends_on_task_id,
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return rowcount > 0

    async def are_dependencies_resolved(
        self, task_id: uuid.UUID
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Check whether all prerequisite dependencies for task_id are in DONE status."""
        prerequisites = await self.list_dependencies(task_id)
        unresolved: list[dict[str, Any]] = []

        for p in prerequisites:
            if p.status != TaskStatus.DONE.value:
                unresolved.append(
                    {
                        "task_id": str(p.id),
                        "title": p.title,
                        "status": p.status,
                    }
                )

        return (len(unresolved) == 0, unresolved)
