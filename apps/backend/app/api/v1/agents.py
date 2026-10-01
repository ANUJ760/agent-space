"""Agent Registry API endpoints for autonomous agents."""

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
from app.config import get_settings
from app.database import get_db_session
from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.agent import Agent
from app.repositories.agent_repo import AgentRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.agent import (
    AgentCreate,
    AgentModelDefaultsResponse,
    AgentResponse,
    AgentUpdate,
)

router = APIRouter()


# ─── Organization-Level Agent Endpoints ─────────────────────────────────────


@router.get(
    "/agents/model-defaults",
    response_model=AgentModelDefaultsResponse,
    summary="Get Agent Model Defaults",
    description=(
        "Returns the default provider, model and endpoint offered when registering an agent. "
        "Contains no secrets: agent API keys are supplied and kept by the client."
    ),
)
async def get_agent_model_defaults(
    actor: CurrentActorDep,
) -> AgentModelDefaultsResponse:
    """Advertise developer-configured defaults for user-supplied (BYOK) agents."""
    defaults = get_settings().agent_model_defaults
    return AgentModelDefaultsResponse(
        provider=defaults.provider,
        model=defaults.model,
        base_url=defaults.base_url,
        user_supplied_keys_enabled=defaults.user_supplied_keys_enabled,
        free_tier_models=list(defaults.free_tier_models),
    )


@router.get(
    "/agents",
    response_model=list[AgentResponse],
    summary="List Organization Agents",
    description="Returns all registered agents in the caller's organization.",
)
async def list_agents(
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
    status_filter: str | None = Query(default=None, alias="status"),
    role_filter: str | None = Query(default=None, alias="role"),
) -> list[AgentResponse]:
    """List agents in the caller's organization."""
    if actor.organization_id is None:
        return []

    agent_repo = AgentRepository(session)
    agents = await agent_repo.list_by_organization(
        actor.organization_id,
        offset=offset,
        limit=limit,
        status=status_filter,
        role=role_filter,
    )
    return [AgentResponse.model_validate(a) for a in agents]


@router.post(
    "/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Agent",
    description="Registers a new autonomous agent definition in the organization.",
)
async def create_agent(
    payload: AgentCreate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentResponse:
    """Create a new agent definition."""
    if actor.organization_id is None:
        raise ForbiddenError("Actor is not associated with an organization.")

    agent_repo = AgentRepository(session)
    project_repo = ProjectRepository(session)

    # If project_id provided, ensure project exists and belongs to the same org
    if payload.project_id is not None:
        project = await project_repo.get_by_id(payload.project_id)
        authorize_project_access(actor, project, Permission.AGENT_MANAGE)

    # Check for unique slug within organization
    existing = await agent_repo.get_by_org_and_slug(actor.organization_id, payload.slug)
    if existing is not None:
        raise ConflictError(
            code="AGENT_SLUG_EXISTS",
            message=f"Agent with slug '{payload.slug}' already exists in this organization.",
            details={"slug": payload.slug},
        )

    agent = Agent(
        organization_id=actor.organization_id,
        project_id=payload.project_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        role=payload.role,
        model=payload.model,
        model_provider=payload.model_provider,
        capabilities=payload.capabilities,
        system_prompt=payload.system_prompt,
        status=payload.status,
        configuration=payload.configuration,
    )
    created = await agent_repo.create(agent)
    return AgentResponse.model_validate(created)


@router.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    summary="Get Agent",
    description="Retrieves an agent definition by ID.",
)
async def get_agent(
    agent_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentResponse:
    """Fetch an agent definition."""
    agent_repo = AgentRepository(session)
    agent = await agent_repo.get_by_id(agent_id)

    authorize_object_access(actor, agent, Permission.AGENT_READ, resource_name="Agent")
    assert agent is not None
    return AgentResponse.model_validate(agent)


@router.patch(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    summary="Update Agent",
    description="Updates agent configuration, model, or capabilities.",
)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentResponse:
    """Update agent configuration."""
    agent_repo = AgentRepository(session)
    agent = await agent_repo.get_by_id(agent_id)

    authorize_object_access(actor, agent, Permission.AGENT_MANAGE, resource_name="Agent")
    assert agent is not None

    if payload.name is not None:
        agent.name = payload.name
    if payload.description is not None:
        agent.description = payload.description
    if payload.role is not None:
        agent.role = payload.role
    if payload.model is not None:
        agent.model = payload.model
    if payload.model_provider is not None:
        agent.model_provider = payload.model_provider
    if payload.capabilities is not None:
        agent.capabilities = payload.capabilities
    if payload.system_prompt is not None:
        agent.system_prompt = payload.system_prompt
    if payload.status is not None:
        agent.status = payload.status
    if payload.configuration is not None:
        agent.configuration = payload.configuration
    if "project_id" in payload.model_fields_set:
        if payload.project_id is None:
            agent.project_id = None
        elif payload.project_id != agent.project_id:
            project_repo = ProjectRepository(session)
            target = await project_repo.get_by_id(payload.project_id)
            if target is None or target.organization_id != actor.organization_id:
                raise NotFoundError(resource="Project", resource_id=str(payload.project_id))
            authorize_project_access(actor, target, Permission.AGENT_MANAGE)
            agent.project_id = payload.project_id

    agent.version += 1
    updated = await agent_repo.update(agent)
    return AgentResponse.model_validate(updated)


@router.delete(
    "/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Agent",
    description="Permanently deletes an agent definition.",
)
async def delete_agent(
    agent_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Delete an agent."""
    agent_repo = AgentRepository(session)
    agent = await agent_repo.get_by_id(agent_id)

    authorize_object_access(actor, agent, Permission.AGENT_MANAGE, resource_name="Agent")
    assert agent is not None

    await agent_repo.delete(agent)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Project-Scoped Agent Endpoints ─────────────────────────────────────────


@router.get(
    "/projects/{project_id}/agents",
    response_model=list[AgentResponse],
    summary="List Project Agents",
    description="Returns all agents available to a specific project.",
)
async def list_project_agents(
    project_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
    include_org_level: bool = True,
) -> list[AgentResponse]:
    """List agents accessible to the project."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.AGENT_READ)
    assert project is not None

    agent_repo = AgentRepository(session)
    agents = await agent_repo.list_by_project(
        project_id,
        project.organization_id,
        offset=offset,
        limit=limit,
        include_org_level=include_org_level,
    )
    return [AgentResponse.model_validate(a) for a in agents]


@router.post(
    "/projects/{project_id}/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project Agent",
    description="Creates an agent scoped specifically to a project.",
)
async def create_project_agent(
    project_id: uuid.UUID,
    payload: AgentCreate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentResponse:
    """Register an agent explicitly scoped to a project."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.AGENT_MANAGE)
    assert project is not None

    agent_repo = AgentRepository(session)
    existing = await agent_repo.get_by_org_and_slug(project.organization_id, payload.slug)
    if existing is not None:
        raise ConflictError(
            code="AGENT_SLUG_EXISTS",
            message=f"Agent with slug '{payload.slug}' already exists in this organization.",
            details={"slug": payload.slug},
        )

    agent = Agent(
        organization_id=project.organization_id,
        project_id=project_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        role=payload.role,
        model=payload.model,
        model_provider=payload.model_provider,
        capabilities=payload.capabilities,
        system_prompt=payload.system_prompt,
        status=payload.status,
        configuration=payload.configuration,
    )
    created = await agent_repo.create(agent)
    return AgentResponse.model_validate(created)


@router.patch(
    "/projects/{project_id}/agents/{agent_id}",
    response_model=AgentResponse,
    summary="Update Project Agent",
    description="Updates a project-scoped agent.",
)
async def update_project_agent(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentResponse:
    """Update a project-scoped agent."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.AGENT_MANAGE)
    assert project is not None

    agent_repo = AgentRepository(session)
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None or agent.project_id != project_id:
        raise NotFoundError(resource="ProjectAgent", resource_id=str(agent_id))

    if payload.name is not None:
        agent.name = payload.name
    if payload.description is not None:
        agent.description = payload.description
    if payload.role is not None:
        agent.role = payload.role
    if payload.model is not None:
        agent.model = payload.model
    if payload.model_provider is not None:
        agent.model_provider = payload.model_provider
    if payload.capabilities is not None:
        agent.capabilities = payload.capabilities
    if payload.system_prompt is not None:
        agent.system_prompt = payload.system_prompt
    if payload.status is not None:
        agent.status = payload.status
    if payload.configuration is not None:
        agent.configuration = payload.configuration

    agent.version += 1
    updated = await agent_repo.update(agent)
    return AgentResponse.model_validate(updated)


@router.delete(
    "/projects/{project_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Project Agent",
    description="Deletes a project-scoped agent.",
)
async def delete_project_agent(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    actor: CurrentActorDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Delete a project-scoped agent."""
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    authorize_project_access(actor, project, Permission.AGENT_MANAGE)
    assert project is not None

    agent_repo = AgentRepository(session)
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None or agent.project_id != project_id:
        raise NotFoundError(resource="ProjectAgent", resource_id=str(agent_id))

    await agent_repo.delete(agent)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
