"""Authentication, registration, and user profile endpoints."""

import asyncio
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import Actor, CurrentUserDep, Role, get_oidc_client, require_role
from app.auth.oidc import OIDCClient
from app.auth.passwords import hash_password, verify_password
from app.database import get_db_session
from app.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest
from app.schemas.organization import OrganizationResponse
from app.schemas.user import UserProfileResponse
from app.services.user_service import reconcile_user

router = APIRouter(tags=["authentication"])


def _slugify(text: str) -> str:
    """Generate a clean URL-friendly slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or f"org-{uuid.uuid4().hex[:6]}"


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    summary="Sign in to Agent Space",
    description="Authenticates credentials against verified user accounts and issues an authentic signed access token.",
)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    oidc_client: Annotated[OIDCClient, Depends(get_oidc_client)],
) -> AuthTokenResponse:
    """Authenticate an existing user account."""
    # 1. Look up user by username or email
    stmt = (
        select(User)
        .where(or_(User.username == payload.username, User.email == payload.username))
        .options(selectinload(User.organization))
    )
    result = await session.execute(stmt)
    db_user = result.scalars().first()

    # 2. Verify account exists
    if db_user is None or not db_user.is_active or not await asyncio.to_thread(
        verify_password, payload.password, db_user.password_hash
    ):
        raise UnauthorizedError("Invalid username or password.")

    # 3. Restrict administrator accounts from using standard login endpoint
    if db_user.role in (Role.ORG_ADMIN.value, Role.SYSTEM_ADMIN.value):
        raise ForbiddenError("Use your administrator sign-in page.")

    # 4. Generate token using the user's authentic database role
    token_roles = [db_user.role, "developer"]

    token = oidc_client.generate_token(
        sub=db_user.external_subject,
        username=db_user.username,
        email=db_user.email,
        roles=token_roles,
    )

    org_resp = OrganizationResponse.model_validate(db_user.organization) if db_user.organization else None

    profile = UserProfileResponse(
        id=db_user.id,
        external_subject=db_user.external_subject,
        email=db_user.email,
        username=db_user.username,
        display_name=db_user.display_name,
        role=db_user.role,
        is_active=db_user.is_active,
        organization=org_resp,
        token_roles=token_roles,
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=86400,
        user=profile,
    )


@router.post(
    "/admin/login",
    response_model=AuthTokenResponse,
    summary="Admin Login (Protected RBAC)",
    description="Authenticates administrator credentials, strictly enforcing ORG_ADMIN or SYSTEM_ADMIN role.",
)
async def admin_login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    oidc_client: Annotated[OIDCClient, Depends(get_oidc_client)],
) -> AuthTokenResponse:
    """Authenticate administrator, verifying that the user holds admin privileges."""
    stmt = (
        select(User)
        .where(or_(User.username == payload.username, User.email == payload.username))
        .options(selectinload(User.organization))
    )
    result = await session.execute(stmt)
    db_user = result.scalars().first()

    if db_user is None or not db_user.is_active or not await asyncio.to_thread(
        verify_password, payload.password, db_user.password_hash
    ):
        raise UnauthorizedError("Invalid administrator credentials.")

    # Strictly enforce that user holds administrator privileges
    if db_user.role not in (Role.ORG_ADMIN.value, Role.SYSTEM_ADMIN.value):
        raise ForbiddenError(
            f"Access denied. User '{db_user.username}' has role '{db_user.role}', but administrator privileges (ORG_ADMIN or SYSTEM_ADMIN) are required."
        )

    token_roles = [db_user.role, "developer", "admin"]
    token = oidc_client.generate_token(
        sub=db_user.external_subject,
        username=db_user.username,
        email=db_user.email,
        roles=token_roles,
    )

    org_resp = OrganizationResponse.model_validate(db_user.organization) if db_user.organization else None

    profile = UserProfileResponse(
        id=db_user.id,
        external_subject=db_user.external_subject,
        email=db_user.email,
        username=db_user.username,
        display_name=db_user.display_name,
        role=db_user.role,
        is_active=db_user.is_active,
        organization=org_resp,
        token_roles=token_roles,
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=86400,
        user=profile,
    )


@router.get(
    "/admin/session",
    response_model=UserProfileResponse,
    summary="Protected Admin Session Verification",
    description="Protected endpoint guarded by require_role(Role.ORG_ADMIN). Returns verified admin profile.",
)
async def get_admin_session(
    actor: Annotated[Actor, Depends(require_role(Role.ORG_ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserProfileResponse:
    """Protected admin endpoint verifying active administrator authorization."""
    stmt = select(User).where(User.id == actor.id).options(selectinload(User.organization))
    result = await session.execute(stmt)
    db_user = result.scalars().first()
    if db_user is None:
        raise NotFoundError(code="USER_NOT_FOUND", message="Admin user record not found.")

    org_resp = OrganizationResponse.model_validate(db_user.organization) if db_user.organization else None

    return UserProfileResponse(
        id=db_user.id,
        external_subject=db_user.external_subject,
        email=db_user.email,
        username=db_user.username,
        display_name=db_user.display_name,
        role=db_user.role,
        is_active=db_user.is_active,
        organization=org_resp,
        token_roles=[actor.role.value, "admin"],
    )


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sign up a new account & workspace",
    description="Registers a new user, provisions or associates their organization, and issues an access token.",
)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    oidc_client: Annotated[OIDCClient, Depends(get_oidc_client)],
) -> AuthTokenResponse:
    """Create a new user account and associated workspace."""
    user_repo = UserRepository(session)
    org_repo = OrganizationRepository(session)

    # 1. Check for duplicates
    existing = await session.execute(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if existing.scalars().first() is not None:
        raise ConflictError(
            code="USER_ALREADY_EXISTS",
            message=f"A user with username '{payload.username}' or email '{payload.email}' already exists.",
        )

    # 2. Provision or resolve Organization
    org_name = payload.organization_name.strip() if payload.organization_name else f"{payload.username}'s Space"
    org_slug = _slugify(org_name)

    existing_org = await org_repo.get_by_slug(org_slug)
    if existing_org is not None:
        raise ConflictError(
            code="WORKSPACE_EXISTS",
            message="This workspace already exists. Ask its administrator for access.",
        )
    new_org = Organization(
        name=org_name,
        slug=org_slug,
        description=f"Workspace organization for {org_name}",
    )
    org = await org_repo.create(new_org)
    user_role = Role.ORG_ADMIN.value

    # 3. Create user
    new_user = User(
        external_subject=f"sub-{payload.username}-{uuid.uuid4().hex[:8]}",
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name or payload.username,
        password_hash=await asyncio.to_thread(hash_password, payload.password),
        role=user_role,
        organization_id=org.id,
        is_active=True,
    )
    db_user = await user_repo.create(new_user)

    # Eager reload
    stmt = select(User).where(User.id == db_user.id).options(selectinload(User.organization))
    res = await session.execute(stmt)
    db_user = res.scalars().one()

    # 4. Generate token
    token_roles = [db_user.role, "developer"]
    if db_user.role in (Role.ORG_ADMIN.value, Role.SYSTEM_ADMIN.value):
        token_roles.append("admin")

    token = oidc_client.generate_token(
        sub=db_user.external_subject,
        username=db_user.username,
        email=db_user.email,
        roles=token_roles,
    )

    org_resp = OrganizationResponse.model_validate(db_user.organization) if db_user.organization else None

    profile = UserProfileResponse(
        id=db_user.id,
        external_subject=db_user.external_subject,
        email=db_user.email,
        username=db_user.username,
        display_name=db_user.display_name,
        role=db_user.role,
        is_active=db_user.is_active,
        organization=org_resp,
        token_roles=token_roles,
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=86400,
        user=profile,
    )


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
    if not db_user.is_active:
        raise ForbiddenError("Account is inactive.")

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
