"""FastAPI authentication and authorization dependencies.

Provides:
- Token extraction and signature verification
- CurrentUserDep (Keycloak token identity)
- CurrentActorDep (database-reconciled principal with organization context)
- Declarative RBAC role and permission guards (require_role, require_permission)
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthenticatedUser
from app.auth.oidc import OIDCClient, get_oidc_client
from app.auth.rbac import (
    ROLE_HIERARCHY,
    Actor,
    Permission,
    Role,
    has_permission,
)
from app.database import get_db_session
from app.errors import ForbiddenError, UnauthorizedError
from app.services.user_service import reconcile_user


def get_token_from_header(request: Request) -> str:
    """Extract raw bearer token from the HTTP Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise UnauthorizedError("Missing Authorization header.")

    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError("Invalid Authorization scheme. Expected 'Bearer <token>'.")

    token = parts[1].strip()
    if not token:
        raise UnauthorizedError("Empty bearer token.")

    return token


async def get_current_user(
    request: Request,
    oidc_client: Annotated[OIDCClient, Depends(get_oidc_client)],
) -> AuthenticatedUser:
    """FastAPI dependency that enforces authentication and returns AuthenticatedUser.

    1. Extracts Bearer token from Authorization header.
    2. Validates signature via JWKS, issuer, audience, and expiration.
    3. Transforms claims into AuthenticatedUser model.
    4. Attaches verified user to request.state.user.
    """
    token = get_token_from_header(request)
    claims = oidc_client.verify_token(token)
    user = oidc_client.claims_to_user(claims)
    request.state.user = user
    return user


async def get_optional_current_user(
    request: Request,
    oidc_client: Annotated[OIDCClient, Depends(get_oidc_client)],
) -> AuthenticatedUser | None:
    """FastAPI dependency that returns AuthenticatedUser if token present, or None if omitted."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    try:
        return await get_current_user(request=request, oidc_client=oidc_client)
    except UnauthorizedError:
        return None


# Dependency Type Aliases
CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUserDep = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]


# ─── RBAC Actor Dependencies ────────────────────────────────────────────────


async def get_current_actor(
    current_user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Actor:
    """Resolve database user and return an active Actor security principal."""
    db_user = await reconcile_user(session, current_user)
    if not db_user.is_active:
        raise ForbiddenError("Account is inactive.")
    try:
        role = Role(db_user.role)
    except ValueError:
        role = Role.MEMBER

    return Actor(
        id=db_user.id,
        external_subject=db_user.external_subject,
        organization_id=db_user.organization_id,
        role=role,
    )


CurrentActorDep = Annotated[Actor, Depends(get_current_actor)]


def require_role(min_role: Role) -> Callable[..., Coroutine[Any, Any, Actor]]:
    """FastAPI dependency factory enforcing a minimum role hierarchy rank."""

    async def _role_guard(actor: CurrentActorDep) -> Actor:
        actor_rank = ROLE_HIERARCHY.get(actor.role, 0)
        required_rank = ROLE_HIERARCHY.get(min_role, 0)
        if actor_rank < required_rank:
            raise ForbiddenError(
                f"Insufficient privilege. Minimum role required: '{min_role.value}'."
            )
        return actor

    return _role_guard


def require_permission(permission: Permission) -> Callable[..., Coroutine[Any, Any, Actor]]:
    """FastAPI dependency factory enforcing a specific permission."""

    async def _permission_guard(actor: CurrentActorDep) -> Actor:
        if not has_permission(actor, permission):
            raise ForbiddenError(f"Missing required permission: '{permission.value}'.")
        return actor

    return _permission_guard
