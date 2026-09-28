"""Organization endpoints for tenant management."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUserDep
from app.database import get_db_session
from app.errors import ConflictError, NotFoundError
from app.models.organization import Organization
from app.repositories.organization_repo import OrganizationRepository
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
)

router = APIRouter(tags=["organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Organization",
    description="Creates a new multi-tenant organization boundary.",
)
async def create_organization(
    payload: OrganizationCreate,
    current_user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrganizationResponse:
    """Create a new Organization after verifying slug and name uniqueness."""
    repo = OrganizationRepository(session)

    existing_slug = await repo.get_by_slug(payload.slug)
    if existing_slug is not None:
        raise ConflictError(
            code="ORGANIZATION_SLUG_CONFLICT",
            message=f"Organization with slug '{payload.slug}' already exists.",
            details={"slug": payload.slug},
        )

    existing_name = await repo.get_by_name(payload.name)
    if existing_name is not None:
        raise ConflictError(
            code="ORGANIZATION_NAME_CONFLICT",
            message=f"Organization with name '{payload.name}' already exists.",
            details={"name": payload.name},
        )

    org = Organization(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
    )
    created = await repo.create(org)
    return OrganizationResponse.model_validate(created)


@router.get(
    "",
    response_model=list[OrganizationResponse],
    summary="List Organizations",
    description="List all active organizations.",
)
async def list_organizations(
    current_user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = 0,
    limit: int = 100,
) -> list[OrganizationResponse]:
    """Return paginated list of organizations."""
    repo = OrganizationRepository(session)
    orgs = await repo.list_all(offset=offset, limit=limit)
    return [OrganizationResponse.model_validate(org) for org in orgs]


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
    summary="Get Organization",
    description="Retrieve organization details by ID.",
)
async def get_organization(
    organization_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrganizationResponse:
    """Fetch an organization by its UUID."""
    repo = OrganizationRepository(session)
    org = await repo.get_by_id(organization_id)
    if org is None:
        raise NotFoundError(resource="Organization", resource_id=str(organization_id))
    return OrganizationResponse.model_validate(org)
