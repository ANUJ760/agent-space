"""Role-Based Access Control (RBAC) and Centralized Authorization Layer.

Defines:
- Standard roles: SYSTEM_ADMIN, ORG_ADMIN, PROJECT_OWNER, PROJECT_ADMIN, MEMBER, VIEWER, AGENT
- Granular permissions for organizations, projects, tasks, and agents
- Permission evaluation matrix
- Centralized authorization functions:
  - authorize_organization_access
  - authorize_project_access
  - authorize_object_access
- Actor abstraction representing authenticated humans and autonomous agents
- FastAPI declarative dependency helpers
"""

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.errors import ForbiddenError, NotFoundError, UnauthorizedError


class Role(StrEnum):
    """Standard system and organization roles."""

    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    PROJECT_OWNER = "PROJECT_OWNER"
    PROJECT_ADMIN = "PROJECT_ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"
    AGENT = "AGENT"


class Permission(StrEnum):
    """Granular action permissions."""

    # Organization permissions
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"
    ORG_MANAGE_MEMBERS = "org:manage_members"
    ORG_CREATE_PROJECT = "org:create_project"

    # Project permissions
    PROJECT_READ = "project:read"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"
    PROJECT_MANAGE_MEMBERS = "project:manage_members"
    PROJECT_CREATE_TASK = "project:create_task"

    # Task permissions
    TASK_READ = "task:read"
    TASK_CREATE = "task:create"
    TASK_UPDATE = "task:update"
    TASK_DELETE = "task:delete"
    TASK_ASSIGN = "task:assign"
    TASK_EXECUTE = "task:execute"

    # Agent permissions
    AGENT_READ = "agent:read"
    AGENT_MANAGE = "agent:manage"
    AGENT_EXECUTE = "agent:execute"


# Role hierarchy rank (higher number = greater system privilege)
ROLE_HIERARCHY: dict[Role, int] = {
    Role.SYSTEM_ADMIN: 100,
    Role.ORG_ADMIN: 80,
    Role.PROJECT_OWNER: 60,
    Role.PROJECT_ADMIN: 50,
    Role.MEMBER: 30,
    Role.AGENT: 20,
    Role.VIEWER: 10,
}

# Role permission grant matrix
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SYSTEM_ADMIN: set(Permission),  # All permissions
    Role.ORG_ADMIN: {
        Permission.ORG_READ,
        Permission.ORG_UPDATE,
        Permission.ORG_DELETE,
        Permission.ORG_MANAGE_MEMBERS,
        Permission.ORG_CREATE_PROJECT,
        Permission.PROJECT_READ,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MANAGE_MEMBERS,
        Permission.PROJECT_CREATE_TASK,
        Permission.TASK_READ,
        Permission.TASK_CREATE,
        Permission.TASK_UPDATE,
        Permission.TASK_DELETE,
        Permission.TASK_ASSIGN,
        Permission.TASK_EXECUTE,
        Permission.AGENT_READ,
        Permission.AGENT_MANAGE,
        Permission.AGENT_EXECUTE,
    },
    Role.PROJECT_OWNER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MANAGE_MEMBERS,
        Permission.PROJECT_CREATE_TASK,
        Permission.TASK_READ,
        Permission.TASK_CREATE,
        Permission.TASK_UPDATE,
        Permission.TASK_DELETE,
        Permission.TASK_ASSIGN,
        Permission.TASK_EXECUTE,
        Permission.AGENT_READ,
        Permission.AGENT_MANAGE,
        Permission.AGENT_EXECUTE,
    },
    Role.PROJECT_ADMIN: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_MANAGE_MEMBERS,
        Permission.PROJECT_CREATE_TASK,
        Permission.TASK_READ,
        Permission.TASK_CREATE,
        Permission.TASK_UPDATE,
        Permission.TASK_DELETE,
        Permission.TASK_ASSIGN,
        Permission.TASK_EXECUTE,
        Permission.AGENT_READ,
        Permission.AGENT_MANAGE,
        Permission.AGENT_EXECUTE,
    },
    Role.MEMBER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_CREATE_TASK,
        Permission.TASK_READ,
        Permission.TASK_CREATE,
        Permission.TASK_UPDATE,
        Permission.TASK_ASSIGN,
        Permission.TASK_EXECUTE,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
    },
    Role.AGENT: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.TASK_READ,
        Permission.TASK_UPDATE,
        Permission.TASK_EXECUTE,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
    },
    Role.VIEWER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.TASK_READ,
        Permission.AGENT_READ,
    },
}


class Actor(BaseModel):
    """Normalized security principal representing the current subject making a request."""

    id: uuid.UUID = Field(description="Internal User or Agent UUID")
    external_subject: str = Field(description="External ID / Keycloak sub or Agent ID")
    organization_id: uuid.UUID | None = Field(default=None, description="Primary tenant boundary")
    role: Role = Field(default=Role.MEMBER, description="Primary organization role")
    project_roles: dict[uuid.UUID, Role] = Field(
        default_factory=dict, description="Project-specific role overrides"
    )
    is_agent: bool = Field(default=False, description="True if actor is an AI agent")

    @property
    def is_system_admin(self) -> bool:
        return self.role == Role.SYSTEM_ADMIN


def has_permission(
    actor: Actor,
    permission: Permission,
    project_id: uuid.UUID | None = None,
) -> bool:
    """Check whether an actor holds a specific permission globally or for a specific project."""
    if actor.is_system_admin:
        return True

    # 1. Check project-specific role override if applicable
    if project_id and project_id in actor.project_roles:
        p_role = actor.project_roles[project_id]
        if permission in ROLE_PERMISSIONS.get(p_role, set()):
            return True

    # 2. Check primary organization role
    return permission in ROLE_PERMISSIONS.get(actor.role, set())


# ─── Centralized Authorization Functions ────────────────────────────────────


def authorize_organization_access(
    actor: Actor | None,
    organization: Any | None,
    permission: Permission,
) -> None:
    """Authorize access to an Organization object.

    Enforces:
    1. Actor must be authenticated (401).
    2. Organization must exist (404).
    3. Actor must belong to the organization (or be SYSTEM_ADMIN) (403).
    4. Actor's role must grant the required permission (403).
    """
    if actor is None:
        raise UnauthorizedError("Authentication required.")

    if organization is None:
        raise NotFoundError(resource="Organization", resource_id="unknown")

    org_id = getattr(organization, "id", None)
    if not actor.is_system_admin and (
        actor.organization_id is None or actor.organization_id != org_id
    ):
        raise ForbiddenError("Cross-organization access denied.")

    if not has_permission(actor, permission):
        raise ForbiddenError(f"Missing required permission: '{permission.value}'.")


def authorize_project_access(
    actor: Actor | None,
    project: Any | None,
    permission: Permission,
) -> None:
    """Authorize access to a Project object.

    Enforces:
    1. Actor must be authenticated (401).
    2. Project must exist (404).
    3. Project must belong to the actor's organization (403).
    4. Actor must have permission via project role, org role, or system admin (403).
    """
    if actor is None:
        raise UnauthorizedError("Authentication required.")

    if project is None:
        raise NotFoundError(resource="Project", resource_id="unknown")

    project_org_id = getattr(project, "organization_id", None)
    project_id = getattr(project, "id", None)

    if not actor.is_system_admin and (
        actor.organization_id is None or actor.organization_id != project_org_id
    ):
        raise ForbiddenError("Cross-organization access denied.")

    if not has_permission(actor, permission, project_id=project_id):
        raise ForbiddenError(f"Missing required permission: '{permission.value}'.")


def authorize_object_access(
    actor: Actor | None,
    obj: Any | None,
    permission: Permission,
    resource_name: str = "Resource",
    org_id_attr: str = "organization_id",
) -> None:
    """Generic centralized object authorizer enforcing tenant isolation and permissions."""
    if actor is None:
        raise UnauthorizedError("Authentication required.")

    if obj is None:
        raise NotFoundError(resource=resource_name, resource_id="unknown")

    object_org_id = getattr(obj, org_id_attr, None)

    if (
        not actor.is_system_admin
        and object_org_id is not None
        and (actor.organization_id is None or actor.organization_id != object_org_id)
    ):
        raise ForbiddenError(f"Cross-organization access to {resource_name} denied.")

    if not has_permission(actor, permission):
        raise ForbiddenError(f"Missing required permission: '{permission.value}'.")
