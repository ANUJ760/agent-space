"""FastAPI authentication dependencies for verifying Keycloak bearer tokens."""

from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import AuthenticatedUser
from app.auth.oidc import OIDCClient, get_oidc_client
from app.errors import UnauthorizedError


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
