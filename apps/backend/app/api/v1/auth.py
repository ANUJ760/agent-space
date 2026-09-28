"""Authentication and user profile endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUserDep
from app.database import get_db_session
from app.schemas.organization import OrganizationResponse
from app.schemas.user import UserProfileResponse
from app.services.user_service import reconcile_user

router = APIRouter(tags=["authentication"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get Current User Profile",
    description="Returns the profile of the currently authenticated actor, reconciling Keycloak identity to internal user and organization.",
)
async def get_me(
    current_user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserProfileResponse:
    """Resolve and return current authenticated user profile and organization."""
    db_user = await reconcile_user(session, current_user)

    org_resp = None
    if db_user.organization is not None:
        org_resp = OrganizationResponse.model_validate(db_user.organization)

    return UserProfileResponse(
        id=db_user.id,
        external_subject=db_user.external_subject,
        email=db_user.email,
        username=db_user.username,
        display_name=db_user.display_name,
        role=db_user.role,
        is_active=db_user.is_active,
        organization=org_resp,
        token_roles=current_user.roles,
    )
