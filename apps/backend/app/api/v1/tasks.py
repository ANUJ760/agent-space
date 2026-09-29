"""Task API endpoints for project tasks, dependencies, assignments, and lifecycle transitions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentActorDep
from app.auth.rbac import (
    Permission,
    authorize_object_access,
    authorize_project_access,
)
from app.database import get_db_session
from app.errors import ConflictError, NotFoundError
from app.models.task import Task
from app.repositories.agent_repo import AgentRepository
from app.repositories.outbox_repo import OutboxRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.task_dependency_repo import TaskDependencyRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.user_repo import UserRepository
from app.schemas.outbox import OutboxEventResponse
from app.schemas.task import (
    AssigneeType,
    TaskAssignRequest,
    TaskCreate,
    TaskHandoffRequest,
    TaskResponse,
    TaskTakeoverRequest,
    TaskTransitionRequest,
    TaskUpdate,
)
from app.schemas.task_dependency import (
    TaskDependencyCreate,
    TaskDependencyResponse,
)
from app.services.task_state_machine import TaskStatus, check_transition_or_raise

router = APIRouter()


# ─── Project Tasks Endpoints ────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/tasks",
    response_model=list[TaskResponse],
    summary="List Project Tasks",
    description="Returns all tasks within a project with optional filtering.",
)
async def list_project_tasks(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
    status_filter: str | None = Query(default=None, alias="status"),
    priority_filter: str | None = Query(default=None, alias="priority"),
    assigned_agent_id: uuid.UUID | None = None,
    assigned_user_id: uuid.UUID | None = None,
) -> list[TaskResponse]:
    """List tasks in a project."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.TASK_READ)
    assert project is not None

    task_repo = TaskRepository(session)
    tasks = await task_repo.list_by_project(
        project_id,
        offset=offset,
        limit=limit,
        status=status_filter,
        priority=priority_filter,
        assigned_agent_id=assigned_agent_id,
        assigned_user_id=assigned_user_id,
    )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Task",
    description="Creates a new task within a project.",
)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskCreate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Create a new task in TODO state."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.TASK_CREATE)
    assert project is not None

    # Validate assigned agent if specified
    if payload.assigned_agent_id is not None:
        agent_repo = AgentRepository(session)
        agent = await agent_repo.get_by_id(payload.assigned_agent_id)
        if agent is None or agent.organization_id != project.organization_id:
            raise NotFoundError(resource="Agent", resource_id=str(payload.assigned_agent_id))

    # Validate assigned user if specified
    if payload.assigned_user_id is not None:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(payload.assigned_user_id)
        if user is None or user.organization_id != project.organization_id:
            raise NotFoundError(resource="User", resource_id=str(payload.assigned_user_id))

    task_repo = TaskRepository(session)
    task = Task(
        organization_id=project.organization_id,
        project_id=project_id,
        title=payload.title,
        description=payload.description,
        status=TaskStatus.TODO.value,
        priority=payload.priority.value
        if hasattr(payload.priority, "value")
        else str(payload.priority),
        assigned_agent_id=payload.assigned_agent_id,
        assigned_user_id=payload.assigned_user_id,
        created_by_id=actor.id,
        context=payload.context,
    )
    created = await task_repo.create(task)

    outbox_repo = OutboxRepository(session)
    await outbox_repo.record_event(
        event_type="task.created",
        aggregate_type="task",
        aggregate_id=created.id,
        payload={
            "task_id": str(created.id),
            "title": created.title,
            "status": created.status,
            "priority": created.priority,
            "project_id": str(created.project_id),
        },
        organization_id=created.organization_id,
        project_id=created.project_id,
        actor_id=actor.id,
    )

    return TaskResponse.model_validate(created)


# ─── Individual Task Endpoints ──────────────────────────────────────────────


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get Task",
    description="Retrieves a task by its ID.",
)
async def get_task(
    task_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Fetch task details."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_READ, resource_name="Task")
    assert task is not None
    return TaskResponse.model_validate(task)


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Update Task",
    description="Updates task properties. Supports state machine checks and optimistic concurrency locking.",
)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Update task details and/or perform state transition with optional optimistic lock."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_UPDATE, resource_name="Task")
    assert task is not None

    # Enforce centralized state machine if status change requested
    if payload.status is not None and payload.status != task.status:
        check_transition_or_raise(current=task.status, requested=payload.status)

        # Execution guard: cannot move to IN_PROGRESS or CLAIMED if prerequisites are incomplete
        if payload.status in {TaskStatus.IN_PROGRESS.value, TaskStatus.CLAIMED.value}:
            dep_repo = TaskDependencyRepository(session)
            resolved, unresolved = await dep_repo.are_dependencies_resolved(task.id)
            if not resolved:
                raise ConflictError(
                    code="TASK_DEPENDENCIES_UNRESOLVED",
                    message="Cannot start task: prerequisite dependencies are not yet completed.",
                    details={"unresolved_dependencies": unresolved},
                )

        task.status = payload.status

    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.priority is not None:
        task.priority = (
            payload.priority.value if hasattr(payload.priority, "value") else str(payload.priority)
        )
    if payload.context is not None:
        task.context = payload.context
    if payload.result is not None:
        task.result = payload.result
    if payload.error_message is not None:
        task.error_message = payload.error_message

    if payload.assigned_agent_id is not None:
        agent_repo = AgentRepository(session)
        agent = await agent_repo.get_by_id(payload.assigned_agent_id)
        if agent is None or agent.organization_id != task.organization_id:
            raise NotFoundError(resource="Agent", resource_id=str(payload.assigned_agent_id))
        task.assigned_agent_id = payload.assigned_agent_id

    if payload.assigned_user_id is not None:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(payload.assigned_user_id)
        if user is None or user.organization_id != task.organization_id:
            raise NotFoundError(resource="User", resource_id=str(payload.assigned_user_id))
        task.assigned_user_id = payload.assigned_user_id

    # Optimistic locking check if client sent expected_version
    if payload.expected_version is not None:
        updated = await task_repo.update_with_optimistic_lock(task, payload.expected_version)
    else:
        task.version += 1
        updated = await task_repo.update(task)

    return TaskResponse.model_validate(updated)


@router.post(
    "/tasks/{task_id}/transition",
    response_model=TaskResponse,
    summary="Transition Task State",
    description="Explicitly transitions task status according to the state machine.",
)
async def transition_task_state(
    task_id: uuid.UUID,
    payload: TaskTransitionRequest,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Execute state machine transition on a task with execution dependency guards."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_UPDATE, resource_name="Task")
    assert task is not None

    check_transition_or_raise(current=task.status, requested=payload.status)

    # Execution dependency guard
    if payload.status in {TaskStatus.IN_PROGRESS.value, TaskStatus.CLAIMED.value}:
        dep_repo = TaskDependencyRepository(session)
        resolved, unresolved = await dep_repo.are_dependencies_resolved(task.id)
        if not resolved:
            raise ConflictError(
                code="TASK_DEPENDENCIES_UNRESOLVED",
                message="Cannot execute task: prerequisite dependencies are not yet completed.",
                details={"unresolved_dependencies": unresolved},
            )

    previous_status = task.status
    task.status = payload.status

    if payload.expected_version is not None:
        updated = await task_repo.update_with_optimistic_lock(task, payload.expected_version)
    else:
        task.version += 1
        updated = await task_repo.update(task)

    outbox_repo = OutboxRepository(session)
    event_type = (
        "task.completed" if payload.status == TaskStatus.DONE.value else "task.transitioned"
    )
    await outbox_repo.record_event(
        event_type=event_type,
        aggregate_type="task",
        aggregate_id=updated.id,
        payload={
            "task_id": str(updated.id),
            "previous_status": previous_status,
            "new_status": updated.status,
            "reason": payload.reason,
        },
        organization_id=updated.organization_id,
        project_id=updated.project_id,
        actor_id=actor.id,
    )

    return TaskResponse.model_validate(updated)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Task",
    description="Permanently deletes a task.",
)
async def delete_task(
    task_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Delete a task."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_DELETE, resource_name="Task")
    assert task is not None

    outbox_repo = OutboxRepository(session)
    await outbox_repo.record_event(
        event_type="task.deleted",
        aggregate_type="task",
        aggregate_id=task.id,
        payload={"task_id": str(task.id), "title": task.title},
        organization_id=task.organization_id,
        project_id=task.project_id,
        actor_id=actor.id,
    )

    await task_repo.delete(task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Task Assignment Endpoints (M15) ────────────────────────────────────────


@router.post(
    "/tasks/{task_id}/assign",
    response_model=TaskResponse,
    summary="Assign Task",
    description="Assigns a task to a human or agent and transitions state to CLAIMED.",
)
async def assign_task(
    task_id: uuid.UUID,
    payload: TaskAssignRequest,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Assign a task to a designated worker using row-level locking (SELECT FOR UPDATE)."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id_for_update(task_id)

    authorize_object_access(actor, task, Permission.TASK_ASSIGN, resource_name="Task")
    assert task is not None

    is_already_assigned = (
        task.assigned_agent_id is not None
        or task.assigned_user_id is not None
        or task.status in {TaskStatus.CLAIMED.value, TaskStatus.IN_PROGRESS.value}
    )
    if is_already_assigned and not payload.allow_takeover:
        raise ConflictError(
            code="TASK_ALREADY_ASSIGNED",
            message="Task is already assigned to a worker or in progress.",
            details={"task_id": str(task.id), "status": task.status},
        )

    if payload.assignee_type == AssigneeType.AGENT:
        agent_repo = AgentRepository(session)
        agent = await agent_repo.get_by_id(payload.assignee_id)
        if agent is None or agent.organization_id != task.organization_id:
            raise NotFoundError(resource="Agent", resource_id=str(payload.assignee_id))
    elif payload.assignee_type == AssigneeType.HUMAN:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(payload.assignee_id)
        if user is None or user.organization_id != task.organization_id:
            raise NotFoundError(resource="User", resource_id=str(payload.assignee_id))

    # Auto-claim task if in TODO
    if task.status == TaskStatus.TODO.value:
        dep_repo = TaskDependencyRepository(session)
        resolved, unresolved = await dep_repo.are_dependencies_resolved(task.id)
        if not resolved:
            raise ConflictError(
                code="TASK_DEPENDENCIES_UNRESOLVED",
                message="Cannot assign and claim task: prerequisite dependencies are not yet completed.",
                details={"unresolved_dependencies": unresolved},
            )

    updated = await task_repo.assign_task_atomic(
        task=task,
        assignee_type=payload.assignee_type.value,
        assignee_id=payload.assignee_id,
        allow_takeover=payload.allow_takeover,
    )

    outbox_repo = OutboxRepository(session)
    await outbox_repo.record_event(
        event_type="task.assigned",
        aggregate_type="task",
        aggregate_id=updated.id,
        payload={
            "task_id": str(updated.id),
            "assignee_type": payload.assignee_type.value,
            "assignee_id": str(payload.assignee_id),
            "status": updated.status,
            "allow_takeover": payload.allow_takeover,
        },
        organization_id=updated.organization_id,
        project_id=updated.project_id,
        actor_id=actor.id,
    )

    return TaskResponse.model_validate(updated)


@router.post(
    "/tasks/{task_id}/release",
    response_model=TaskResponse,
    summary="Release Task",
    description="Clears assignment and returns task to TODO state.",
)
async def release_task(
    task_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Release a claimed task back to the backlog."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_ASSIGN, resource_name="Task")
    assert task is not None

    task.assigned_agent_id = None
    task.assigned_user_id = None

    if task.status == TaskStatus.CLAIMED.value:
        task.status = TaskStatus.TODO.value

    task.version += 1
    updated = await task_repo.update(task)

    outbox_repo = OutboxRepository(session)
    await outbox_repo.record_event(
        event_type="task.released",
        aggregate_type="task",
        aggregate_id=updated.id,
        payload={
            "task_id": str(updated.id),
            "status": updated.status,
        },
        organization_id=updated.organization_id,
        project_id=updated.project_id,
        actor_id=actor.id,
    )

    return TaskResponse.model_validate(updated)


# ─── Task Dependencies Endpoints (M14) ──────────────────────────────────────


@router.get(
    "/tasks/{task_id}/dependencies",
    response_model=list[TaskResponse],
    summary="List Task Dependencies",
    description="Returns all prerequisite tasks that this task depends on.",
)
async def list_task_dependencies(
    task_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TaskResponse]:
    """List prerequisite tasks."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_READ, resource_name="Task")
    assert task is not None

    dep_repo = TaskDependencyRepository(session)
    prerequisites = await dep_repo.list_dependencies(task_id)
    return [TaskResponse.model_validate(p) for p in prerequisites]


@router.post(
    "/tasks/{task_id}/dependencies",
    response_model=TaskDependencyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Task Dependency",
    description="Establishes a prerequisite dependency edge preventing task DAG cycles.",
)
async def add_task_dependency(
    task_id: uuid.UUID,
    payload: TaskDependencyCreate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskDependencyResponse:
    """Add a directed prerequisite dependency edge."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_UPDATE, resource_name="Task")
    assert task is not None

    # Validate prerequisite task exists and belongs to the same project
    prerequisite_task = await task_repo.get_by_id(payload.depends_on_task_id)
    if prerequisite_task is None or prerequisite_task.project_id != task.project_id:
        raise NotFoundError(
            resource="PrerequisiteTask", resource_id=str(payload.depends_on_task_id)
        )

    dep_repo = TaskDependencyRepository(session)
    dep = await dep_repo.add_dependency(task_id, payload.depends_on_task_id)
    return TaskDependencyResponse.model_validate(dep)


@router.delete(
    "/tasks/{task_id}/dependencies/{dependency_task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove Task Dependency",
    description="Removes a prerequisite dependency edge.",
)
async def remove_task_dependency(
    task_id: uuid.UUID,
    dependency_task_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Remove a dependency edge."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    authorize_object_access(actor, task, Permission.TASK_UPDATE, resource_name="Task")
    assert task is not None

    dep_repo = TaskDependencyRepository(session)
    removed = await dep_repo.remove_dependency(task_id, dependency_task_id)
    if not removed:
        raise NotFoundError(resource="TaskDependency", resource_id=str(dependency_task_id))

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Audit Outbox Endpoints (M19) ───────────────────────────────────────────


@router.get(
    "/projects/{project_id}/audit-events",
    response_model=list[OutboxEventResponse],
    summary="List Project Audit Events",
    description="Returns recorded domain outbox events for audit tracking and compliance.",
)
async def list_project_audit_events(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
) -> list[OutboxEventResponse]:
    """Retrieve audit outbox events for a project."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.TASK_READ)
    assert project is not None

    outbox_repo = OutboxRepository(session)
    events = await outbox_repo.list_by_project(project_id, offset=offset, limit=limit)
    return [OutboxEventResponse.model_validate(e) for e in events]


# ─── Human Takeover & Handoff Endpoints (M53 / M54) ─────────────────────────


@router.post(
    "/tasks/{task_id}/takeover",
    response_model=TaskResponse,
    summary="Human Task Takeover",
    description="Atomically takes over a task from an agent by a human user with row locking and audit logging.",
)
async def human_takeover(
    task_id: uuid.UUID,
    payload: TaskTakeoverRequest,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Atomically seize control of a task currently assigned to an agent."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    authorize_object_access(actor, task, Permission.TASK_ASSIGN, resource_name="Task")
    assert task is not None

    previous_agent = task.assigned_agent_id

    # Atomic row-lock takeover
    updated = await task_repo.takeover_task_atomic(
        task_id=task_id,
        user_id=actor.id,
        expected_version=payload.expected_version,
    )

    outbox_repo = OutboxRepository(session)
    await outbox_repo.record_event(
        event_type="task.takeover",
        aggregate_type="task",
        aggregate_id=updated.id,
        payload={
            "task_id": str(updated.id),
            "user_id": str(actor.id),
            "previous_agent_id": str(previous_agent) if previous_agent else None,
            "reason": payload.reason,
            "status": updated.status,
            "version": updated.version,
        },
        organization_id=updated.organization_id,
        project_id=updated.project_id,
        actor_id=actor.id,
    )

    return TaskResponse.model_validate(updated)


@router.post(
    "/tasks/{task_id}/handoff",
    response_model=TaskResponse,
    summary="Human to Agent Handoff",
    description="Atomically hands off a task from the human assignee back to an agent with instructions.",
)
async def human_handoff(
    task_id: uuid.UUID,
    payload: TaskHandoffRequest,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Hand off task ownership from the human user back to an agent."""
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    authorize_object_access(actor, task, Permission.TASK_ASSIGN, resource_name="Task")
    assert task is not None

    agent_repo = AgentRepository(session)
    agent = await agent_repo.get_by_id(payload.agent_id)
    if not agent:
        raise NotFoundError(resource="Agent", resource_id=str(payload.agent_id))

    updated = await task_repo.handoff_task_atomic(
        task_id=task_id,
        user_id=actor.id,
        agent_id=payload.agent_id,
        instructions=payload.instructions,
    )

    outbox_repo = OutboxRepository(session)
    await outbox_repo.record_event(
        event_type="task.handoff",
        aggregate_type="task",
        aggregate_id=updated.id,
        payload={
            "task_id": str(updated.id),
            "user_id": str(actor.id),
            "agent_id": str(payload.agent_id),
            "instructions": payload.instructions,
            "status": updated.status,
            "version": updated.version,
        },
        organization_id=updated.organization_id,
        project_id=updated.project_id,
        actor_id=actor.id,
    )

    return TaskResponse.model_validate(updated)

