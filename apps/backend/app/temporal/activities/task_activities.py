"""Task lifecycle activities for Temporal TaskWorkflow."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from temporalio import activity

from app.database import get_db_manager
from app.repositories.task_dependency_repo import TaskDependencyRepository
from app.repositories.task_repo import TaskRepository

logger = structlog.stdlib.get_logger(__name__)


@activity.defn
async def load_task_activity(task_id_str: str) -> dict[str, Any]:
    """Activity 1: Load task from database and return metadata."""
    task_id = uuid.UUID(task_id_str)
    db_mgr = get_db_manager()

    async with db_mgr.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id_str} not found")
        return {
            "id": str(task.id),
            "project_id": str(task.project_id),
            "title": task.title,
            "status": task.status,
            "version": task.version,
            "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
        }


@activity.defn
async def validate_dependencies_activity(task_id_str: str) -> dict[str, Any]:
    """Activity 2: Verify all upstream dependencies are completed (DONE)."""
    task_id = uuid.UUID(task_id_str)
    db_mgr = get_db_manager()

    async with db_mgr.session_factory() as session:
        dep_repo = TaskDependencyRepository(session)
        resolved, unresolved = await dep_repo.are_dependencies_resolved(task_id)
        if not resolved:
            unmet_ids = [u["task_id"] for u in unresolved]
            logger.warning("dependencies_unmet", task_id=task_id_str, unmet_ids=unmet_ids)
            return {
                "valid": False,
                "unmet_dependencies": unmet_ids,
            }

        return {"valid": True, "unmet_dependencies": []}


@activity.defn
async def claim_task_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Activity 3: Claim task for the specified agent using atomic assignment."""
    task_id = uuid.UUID(payload["task_id"])
    agent_id = uuid.UUID(payload["agent_id"])

    db_mgr = get_db_manager()
    async with db_mgr.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        claimed_task = await repo.assign_task_atomic(
            task=task,
            assignee_type="AGENT",
            assignee_id=agent_id,
        )
        await session.commit()
        return {
            "id": str(claimed_task.id),
            "status": claimed_task.status,
            "version": claimed_task.version,
            "assigned_agent_id": str(claimed_task.assigned_agent_id),
        }


@activity.defn
async def execute_worker_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Activity 4: Execute worker logic for task, transitioning IN_PROGRESS -> REVIEW."""
    task_id = uuid.UUID(payload["task_id"])

    db_mgr = get_db_manager()
    async with db_mgr.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Transition CLAIMED -> IN_PROGRESS
        if task.status == "CLAIMED":
            task.status = "IN_PROGRESS"
            task.version += 1
            await session.commit()

        # Simulate / execute agent work steps
        logger.info("executing_worker_activity", task_id=str(task_id))

        # Transition IN_PROGRESS -> REVIEW
        task.status = "REVIEW"
        task.version += 1
        await session.commit()

        return {
            "id": str(task.id),
            "status": task.status,
            "version": task.version,
            "output_summary": "Task execution successfully finished by agent",
        }


@activity.defn
async def finish_task_activity(task_id_str: str) -> dict[str, Any]:
    """Activity 5: Finalize task transition to DONE."""
    task_id = uuid.UUID(task_id_str)
    db_mgr = get_db_manager()

    async with db_mgr.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id_str} not found")

        task.status = "DONE"
        task.version += 1
        await session.commit()

        return {
            "id": str(task.id),
            "status": task.status,
            "version": task.version,
        }
