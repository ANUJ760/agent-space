"""Repository for Task database operations."""

import uuid

from sqlalchemy import func, select, update

from app.errors import ConflictError
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

    async def get_by_id_for_update(self, task_id: uuid.UUID) -> Task | None:
        """Fetch task by ID with an exclusive row-level lock (SELECT ... FOR UPDATE)."""
        stmt = select(Task).where(Task.id == task_id).with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign_task_atomic(
        self,
        task: Task,
        assignee_type: str,
        assignee_id: uuid.UUID,
        allow_takeover: bool = False,
    ) -> Task:
        """Assign a task atomically with row-level locking and race-free concurrency guards.

        Ensures that when 20+ workers attempt simultaneous assignment on an unassigned task,
        exactly one worker succeeds and all concurrent competitors receive TASK_ALREADY_ASSIGNED.
        """
        assigned_agent = assignee_id if assignee_type == "AGENT" else None
        assigned_user = assignee_id if assignee_type == "HUMAN" else None

        if allow_takeover:
            task.assigned_agent_id = assigned_agent
            task.assigned_user_id = assigned_user
            if task.status == "TODO":
                task.status = "CLAIMED"
            task.version += 1
            return await self.update(task)

        # Atomic CAS mutation: ensures exactly one winner
        stmt = (
            update(Task)
            .where(
                Task.id == task.id,
                Task.version == task.version,
                Task.assigned_agent_id.is_(None),
                Task.assigned_user_id.is_(None),
                Task.status == "TODO",
            )
            .values(
                assigned_agent_id=assigned_agent,
                assigned_user_id=assigned_user,
                status="CLAIMED",
                version=task.version + 1,
                updated_at=func.now(),
            )
        )
        result = await self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        if rowcount == 0:
            raise ConflictError(
                code="TASK_ALREADY_ASSIGNED",
                message="Task is already assigned to a worker or in progress.",
                details={"task_id": str(task.id)},
            )
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def update_with_optimistic_lock(self, task: Task, expected_version: int) -> Task:
        """Update a task atomically verifying optimistic concurrency version.

        Executes:
            UPDATE tasks SET ... WHERE id = :id AND version = :expected_version
        Raises ConflictError(code="TASK_VERSION_CONFLICT") if zero rows were updated.
        """
        stmt = (
            update(Task)
            .where(Task.id == task.id, Task.version == expected_version)
            .values(
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                assigned_agent_id=task.assigned_agent_id,
                assigned_user_id=task.assigned_user_id,
                context=task.context,
                result=task.result,
                error_message=task.error_message,
                version=expected_version + 1,
                updated_at=func.now(),
            )
        )
        result = await self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        if rowcount == 0:
            raise ConflictError(
                code="TASK_VERSION_CONFLICT",
                message=f"Task version conflict: expected version {expected_version}, but task has been modified.",
                details={"task_id": str(task.id), "expected_version": expected_version},
            )
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def takeover_task_atomic(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_version: int | None = None,
    ) -> Task:
        """Atomically take over a task from an agent by a human user.

        Ensures race-free concurrency:
        If two users attempt takeover simultaneously, exactly one succeeds and the other receives ConflictError.
        """
        task = await self.get_by_id_for_update(task_id)
        if not task:
            from app.errors import NotFoundError
            raise NotFoundError(code="TASK_NOT_FOUND", message=f"Task {task_id} not found")

        if expected_version is not None and task.version != expected_version:
            raise ConflictError(
                code="TAKEOVER_CONFLICT",
                message=f"Task version conflict during takeover: expected {expected_version}, got {task.version}",
                details={"task_id": str(task_id), "version": task.version},
            )

        if task.assigned_user_id is not None and task.assigned_user_id != user_id:
            raise ConflictError(
                code="TAKEOVER_CONFLICT",
                message=f"Task is already taken over by user {task.assigned_user_id}",
                details={"task_id": str(task_id), "current_owner": str(task.assigned_user_id)},
            )

        task.assigned_user_id = user_id
        task.assigned_agent_id = None
        task.status = "IN_PROGRESS"
        task.version += 1
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def handoff_task_atomic(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
        instructions: str | None = None,
    ) -> Task:
        """Atomically hand off a task from a human user back to an agent."""
        task = await self.get_by_id_for_update(task_id)
        if not task:
            from app.errors import NotFoundError
            raise NotFoundError(code="TASK_NOT_FOUND", message=f"Task {task_id} not found")

        if task.assigned_user_id != user_id:
            raise ConflictError(
                code="HANDOFF_UNAUTHORIZED",
                message="Cannot hand off task: caller is not the currently assigned user",
                details={"task_id": str(task_id)},
            )

        task.assigned_user_id = None
        task.assigned_agent_id = agent_id
        task.status = "CLAIMED"
        if instructions:
            ctx = dict(task.context or {})
            ctx["handoff_instructions"] = instructions
            task.context = ctx
        task.version += 1
        await self._session.flush()
        await self._session.refresh(task)
        return task

