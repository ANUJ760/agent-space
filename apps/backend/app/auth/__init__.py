"""Authentication package for Keycloak OIDC integration."""

from app.auth.dependencies import (
    CurrentUserDep,
    OptionalUserDep,
    get_current_user,
    get_optional_current_user,
    get_token_from_header,
)
from app.auth.models import AuthenticatedUser
from app.auth.oidc import OIDCClient, get_oidc_client, set_oidc_client

__all__ = [
    "AuthenticatedUser",
    "CurrentUserDep",
    "OIDCClient",
    "OptionalUserDep",
    "get_current_user",
    "get_oidc_client",
    "get_optional_current_user",
    "get_token_from_header",
    "set_oidc_client",
]
