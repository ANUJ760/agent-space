"""Authentication and RBAC authorization package for Agent Space."""

from app.auth.dependencies import (
    CurrentActorDep,
    CurrentUserDep,
    OptionalUserDep,
    get_current_actor,
    get_current_user,
    get_optional_current_user,
    get_token_from_header,
    require_permission,
    require_role,
)
from app.auth.models import AuthenticatedUser
from app.auth.oidc import OIDCClient, get_oidc_client, set_oidc_client
from app.auth.rbac import (
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    Actor,
    Permission,
    Role,
    authorize_object_access,
    authorize_organization_access,
    authorize_project_access,
    has_permission,
)

__all__ = [
    "ROLE_HIERARCHY",
    "ROLE_PERMISSIONS",
    "Actor",
    "AuthenticatedUser",
    "CurrentActorDep",
    "CurrentUserDep",
    "OIDCClient",
    "OptionalUserDep",
    "Permission",
    "Role",
    "authorize_object_access",
    "authorize_organization_access",
    "authorize_project_access",
    "get_current_actor",
    "get_current_user",
    "get_oidc_client",
    "get_optional_current_user",
    "get_token_from_header",
    "has_permission",
    "require_permission",
    "require_role",
    "set_oidc_client",
]
