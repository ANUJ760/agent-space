"""Project membership endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentActorDep, Permission, authorize_project_access
from app.database import get_db_session
from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.project_member import ProjectMember
from app.repositories.project_member_repo import ProjectMemberRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.user_repo import UserRepository
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
)

router = APIRouter(tags=["project-members"])


@router.get(
    "/{project_id}/members",
    response_model=list[ProjectMemberResponse],
    summary="List Project Members",
    description="Lists all users assigned to a project.",
)
async def list_project_members(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
) -> list[ProjectMemberResponse]:
    """List members of a project."""
    project_repo = ProjectRepository(session)
    member_repo = ProjectMemberRepository(session)

    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.PROJECT_READ)

    members = await member_repo.list_by_project(project_id, offset=offset, limit=limit)
    return [
        ProjectMemberResponse(
            id=m.id,
            project_id=m.project_id,
            user_id=m.user_id,
            role=m.role,
            username=m.user.username if m.user else None,
            email=m.user.email if m.user else None,
            created_at=m.created_at,
            updated_at=m.updated_at,
            version=m.version,
        )
        for m in members
    ]


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Project Member",
    description="Assigns a user from the same organization to the project.",
)
async def add_project_member(
    project_id: uuid.UUID,
    payload: ProjectMemberCreate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectMemberResponse:
    """Add a member to a project after validating tenant boundary and role permissions."""
    project_repo = ProjectRepository(session)
    member_repo = ProjectMemberRepository(session)
    user_repo = UserRepository(session)

    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.PROJECT_MANAGE_MEMBERS)
    assert project is not None

    # Validate that target user exists and belongs to the project's organization
    target_user = await user_repo.get_by_id(payload.user_id)
    if target_user is None:
        raise NotFoundError(resource="User", resource_id=str(payload.user_id))

    if target_user.organization_id != project.organization_id:
        raise ForbiddenError("Cannot add a user from a different organization to this project.")

    # Check duplicate membership
    existing_membership = await member_repo.get_by_project_and_user(project_id, payload.user_id)
    if existing_membership is not None:
        raise ConflictError(
            code="USER_ALREADY_MEMBER",
            message=f"User '{target_user.username}' is already a member of this project.",
            details={"user_id": str(payload.user_id), "project_id": str(project_id)},
        )

    member = ProjectMember(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    created = await member_repo.create(member)
    return ProjectMemberResponse(
        id=created.id,
        project_id=created.project_id,
        user_id=created.user_id,
        role=created.role,
        username=target_user.username,
        email=target_user.email,
        created_at=created.created_at,
        updated_at=created.updated_at,
        version=created.version,
    )


@router.patch(
    "/{project_id}/members/{user_id}",
    response_model=ProjectMemberResponse,
    summary="Update Member Role",
    description="Updates a member's role within the project.",
)
async def update_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProjectMemberUpdate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectMemberResponse:
    """Update role for an existing project member."""
    project_repo = ProjectRepository(session)
    member_repo = ProjectMemberRepository(session)

    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.PROJECT_MANAGE_MEMBERS)

    membership = await member_repo.get_by_project_and_user(project_id, user_id)
    if membership is None:
        raise NotFoundError(resource="ProjectMember", resource_id=str(user_id))

    # Guard: prevent demoting the sole PROJECT_OWNER
    if membership.role == "PROJECT_OWNER" and payload.role != "PROJECT_OWNER":
        owner_count = await member_repo.count_owners(project_id)
        if owner_count <= 1:
            raise ConflictError(
                code="LAST_OWNER_DEMOTION",
                message="Cannot demote the sole project owner. Promote another member first.",
            )

    membership.role = payload.role
    membership.version += 1
    updated = await member_repo.update(membership)

    return ProjectMemberResponse(
        id=updated.id,
        project_id=updated.project_id,
        user_id=updated.user_id,
        role=updated.role,
        username=membership.user.username if membership.user else None,
        email=membership.user.email if membership.user else None,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        version=updated.version,
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove Project Member",
    description="Removes a user from a project.",
)
async def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Remove a member from a project."""
    project_repo = ProjectRepository(session)
    member_repo = ProjectMemberRepository(session)

    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.PROJECT_MANAGE_MEMBERS)

    membership = await member_repo.get_by_project_and_user(project_id, user_id)
    if membership is None:
        raise NotFoundError(resource="ProjectMember", resource_id=str(user_id))

    # Guard: prevent removing the sole PROJECT_OWNER
    if membership.role == "PROJECT_OWNER":
        owner_count = await member_repo.count_owners(project_id)
        if owner_count <= 1:
            raise ConflictError(
                code="LAST_OWNER_REMOVAL",
                message="Cannot remove the sole project owner.",
            )

    await member_repo.delete(membership)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
