"""Project management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentActorDep, Permission, Role, authorize_project_access
from app.database import get_db_session
from app.errors import ConflictError, ForbiddenError
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.repositories.project_member_repo import ProjectMemberRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdate,
)

router = APIRouter(tags=["projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project",
    description="Creates a new project in the current actor's organization and assigns creator as PROJECT_OWNER.",
)
async def create_project(
    payload: ProjectCreate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse:
    """Create a new project strictly scoped to the actor's organization."""
    if actor.organization_id is None:
        raise ForbiddenError("Actor does not belong to any organization.")

    project_repo = ProjectRepository(session)
    member_repo = ProjectMemberRepository(session)

    # Check slug uniqueness within organization
    existing = await project_repo.get_by_slug_and_org(payload.slug, actor.organization_id)
    if existing is not None:
        raise ConflictError(
            code="PROJECT_SLUG_CONFLICT",
            message=f"Project with slug '{payload.slug}' already exists in this organization.",
            details={"slug": payload.slug},
        )

    project = Project(
        organization_id=actor.organization_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        repository_url=payload.repository_url,
        default_branch=payload.default_branch,
        created_by_id=actor.id,
    )
    created_project = await project_repo.create(project)

    # Automatically assign the creator as PROJECT_OWNER
    owner_member = ProjectMember(
        project_id=created_project.id,
        user_id=actor.id,
        role=Role.PROJECT_OWNER.value,
    )
    await member_repo.create(owner_member)

    return ProjectResponse.model_validate(created_project)


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List Projects",
    description="Lists all projects belonging to the actor's organization.",
)
async def list_projects(
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
) -> list[ProjectResponse]:
    """Return all projects in the caller's organization."""
    if actor.organization_id is None:
        return []

    project_repo = ProjectRepository(session)
    projects = await project_repo.list_by_organization(
        actor.organization_id, offset=offset, limit=limit
    )
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get Project",
    description="Retrieves a project by ID with organization boundary and role authorization.",
)
async def get_project(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse:
    """Fetch project ensuring tenant isolation and read permission."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)

    authorize_project_access(actor, project, Permission.PROJECT_READ)
    assert project is not None
    return ProjectResponse.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update Project",
    description="Updates project metadata. Requires PROJECT_UPDATE permission.",
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse:
    """Update project details."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)

    authorize_project_access(actor, project, Permission.PROJECT_UPDATE)
    assert project is not None

    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.status is not None:
        project.status = payload.status
    if payload.repository_url is not None:
        project.repository_url = payload.repository_url
    if payload.default_branch is not None:
        project.default_branch = payload.default_branch

    project.version += 1
    updated = await project_repo.update(project)
    return ProjectResponse.model_validate(updated)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Project",
    description="Deletes a project. Requires PROJECT_DELETE permission.",
)
async def delete_project(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Delete project permanently."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)

    authorize_project_access(actor, project, Permission.PROJECT_DELETE)
    assert project is not None

    await project_repo.delete(project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/summary",
    response_model=ProjectSummaryResponse,
    summary="Get Project Summary",
    description="Returns executive metrics for a project including member count.",
)
async def get_project_summary(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectSummaryResponse:
    """Return summary statistics for a project."""
    project_repo = ProjectRepository(session)
    member_repo = ProjectMemberRepository(session)

    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.PROJECT_READ)
    assert project is not None

    member_count = await member_repo.count_by_project(project_id)

    return ProjectSummaryResponse(
        project=ProjectResponse.model_validate(project),
        member_count=member_count,
        task_count=0,
        agent_count=0,
        status=project.status,
    )
