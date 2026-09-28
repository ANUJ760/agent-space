"""Tests for M08 — RBAC / Object Authorization.

Validates the centralized authorization layer against all 5 required test cases:
1. Correct role: access granted.
2. Wrong role: access denied with 403 Forbidden.
3. Wrong organization: cross-tenant access denied with 403 Forbidden.
4. Unauthenticated: access denied with 401 Unauthorized.
5. Unknown object: raises 404 Not Found.

Also validates:
- Role hierarchy (SYSTEM_ADMIN > ORG_ADMIN > PROJECT_OWNER > PROJECT_ADMIN > MEMBER > AGENT > VIEWER)
- Permission matrix evaluation
- System admin cross-organization bypass
- Declarative route guards: require_role and require_permission
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.auth import (
    Actor,
    OIDCClient,
    Permission,
    Role,
    authorize_object_access,
    authorize_organization_access,
    authorize_project_access,
    require_permission,
    require_role,
    set_oidc_client,
)
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager
from app.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.main import create_app
from app.models.organization import Organization
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

# ─── Mock Objects for Object Authorization Testing ──────────────────────────


@dataclass
class MockOrganization:
    id: uuid.UUID
    name: str = "Test Org"


@dataclass
class MockProject:
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str = "Test Project"


# ─── 1. Unit Tests for Centralized Authorization Layer ──────────────────────


class TestCentralizedAuthorizer:
    @pytest.fixture()
    def org_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture()
    def other_org_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture()
    def org(self, org_id: uuid.UUID) -> MockOrganization:
        return MockOrganization(id=org_id)

    @pytest.fixture()
    def project(self, org_id: uuid.UUID) -> MockProject:
        return MockProject(id=uuid.uuid4(), organization_id=org_id)

    # 1. Correct Role -> Access Granted
    def test_correct_role_grants_access(
        self, org_id: uuid.UUID, org: MockOrganization, project: MockProject
    ) -> None:
        admin_actor = Actor(
            id=uuid.uuid4(),
            external_subject="sub-admin",
            organization_id=org_id,
            role=Role.ORG_ADMIN,
        )
        # Should not raise
        authorize_organization_access(admin_actor, org, Permission.ORG_UPDATE)
        authorize_project_access(admin_actor, project, Permission.PROJECT_DELETE)

        member_actor = Actor(
            id=uuid.uuid4(),
            external_subject="sub-member",
            organization_id=org_id,
            role=Role.MEMBER,
        )
        authorize_project_access(member_actor, project, Permission.PROJECT_READ)
        authorize_project_access(member_actor, project, Permission.TASK_CREATE)

    # 2. Wrong Role -> 403 Forbidden
    def test_wrong_role_denies_access(
        self, org_id: uuid.UUID, org: MockOrganization, project: MockProject
    ) -> None:
        viewer_actor = Actor(
            id=uuid.uuid4(),
            external_subject="sub-viewer",
            organization_id=org_id,
            role=Role.VIEWER,
        )
        with pytest.raises(ForbiddenError, match="Missing required permission"):
            authorize_organization_access(viewer_actor, org, Permission.ORG_UPDATE)

        with pytest.raises(ForbiddenError, match="Missing required permission"):
            authorize_project_access(viewer_actor, project, Permission.PROJECT_DELETE)

        member_actor = Actor(
            id=uuid.uuid4(),
            external_subject="sub-member",
            organization_id=org_id,
            role=Role.MEMBER,
        )
        with pytest.raises(ForbiddenError, match="Missing required permission"):
            authorize_project_access(member_actor, project, Permission.PROJECT_DELETE)

    # 3. Wrong Organization -> 403 Forbidden (Cross-Tenant Isolation)
    def test_wrong_organization_denies_access(
        self, other_org_id: uuid.UUID, org: MockOrganization, project: MockProject
    ) -> None:
        foreign_admin = Actor(
            id=uuid.uuid4(),
            external_subject="foreign-sub",
            organization_id=other_org_id,
            role=Role.ORG_ADMIN,
        )
        with pytest.raises(ForbiddenError, match="Cross-organization access denied"):
            authorize_organization_access(foreign_admin, org, Permission.ORG_READ)

        with pytest.raises(ForbiddenError, match="Cross-organization access denied"):
            authorize_project_access(foreign_admin, project, Permission.PROJECT_READ)

    # 4. Unauthenticated -> 401 Unauthorized
    def test_unauthenticated_actor_denies_access(
        self, org: MockOrganization, project: MockProject
    ) -> None:
        with pytest.raises(UnauthorizedError, match="Authentication required"):
            authorize_organization_access(None, org, Permission.ORG_READ)

        with pytest.raises(UnauthorizedError, match="Authentication required"):
            authorize_project_access(None, project, Permission.PROJECT_READ)

    # 5. Unknown Object -> 404 Not Found
    def test_unknown_object_raises_not_found(self, org_id: uuid.UUID) -> None:
        actor = Actor(
            id=uuid.uuid4(),
            external_subject="sub-1",
            organization_id=org_id,
            role=Role.ORG_ADMIN,
        )
        with pytest.raises(NotFoundError, match="Organization not found"):
            authorize_organization_access(actor, None, Permission.ORG_READ)

        with pytest.raises(NotFoundError, match="Project not found"):
            authorize_project_access(actor, None, Permission.PROJECT_READ)

        with pytest.raises(NotFoundError, match="Task not found"):
            authorize_object_access(actor, None, Permission.TASK_READ, resource_name="Task")

    # System Admin cross-org bypass
    def test_system_admin_bypasses_organization_boundary(
        self, other_org_id: uuid.UUID, org: MockOrganization, project: MockProject
    ) -> None:
        sys_admin = Actor(
            id=uuid.uuid4(),
            external_subject="sys-admin",
            organization_id=other_org_id,
            role=Role.SYSTEM_ADMIN,
        )
        # Should succeed even though org_id differs
        authorize_organization_access(sys_admin, org, Permission.ORG_DELETE)
        authorize_project_access(sys_admin, project, Permission.PROJECT_DELETE)


# ─── 2. FastAPI Declarative Route Guards Tests ──────────────────────────────


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey, bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pem_priv = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_pub = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key, pem_priv, pem_pub


@pytest.fixture()
def oidc_setup(rsa_keys: tuple[Any, Any, bytes, bytes]) -> Iterator[OIDCClient]:
    _, public_key, _, _ = rsa_keys
    settings = KeycloakSettings(
        server_url="http://localhost:8080",
        realm="agentspace",
        client_id="agentspace-backend",
        audience="agentspace-backend",
    )
    client = OIDCClient(settings)
    client.register_mock_key("key-1", public_key)
    set_oidc_client(client)
    yield client
    client.clear_mock_keys()
    set_oidc_client(None)


def sign_token(pem_priv: bytes, sub: str, roles: list[str] | None = None) -> str:
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": sub,
        "email": f"{sub}@example.com",
        "email_verified": True,
        "realm_access": {"roles": roles or []},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def rbac_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID]]:
    """Set up app with two organizations and users with different roles."""
    db_path = tmp_path / "rbac_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    settings = Settings(
        environment="test",
        debug=True,
        log_format="text",
        database_url=db_url,
    )
    db = DatabaseManager(settings.database)
    await db.connect()
    await db.create_all()

    # Pre-populate Org A and Org B
    async with db.session_factory() as session:
        org_a = Organization(name="Org A", slug="org-a")
        org_b = Organization(name="Org B", slug="org-b")
        session.add_all([org_a, org_b])
        await session.flush()

        # Users in Org A
        admin_a = User(
            external_subject="sub-admin-a",
            username="admin_a",
            email="admin_a@a.com",
            role=Role.ORG_ADMIN.value,
            organization_id=org_a.id,
        )
        member_a = User(
            external_subject="sub-member-a",
            username="member_a",
            email="member_a@a.com",
            role=Role.MEMBER.value,
            organization_id=org_a.id,
        )
        viewer_a = User(
            external_subject="sub-viewer-a",
            username="viewer_a",
            email="viewer_a@a.com",
            role=Role.VIEWER.value,
            organization_id=org_a.id,
        )

        # User in Org B
        member_b = User(
            external_subject="sub-member-b",
            username="member_b",
            email="member_b@b.com",
            role=Role.MEMBER.value,
            organization_id=org_b.id,
        )

        session.add_all([admin_a, member_a, viewer_a, member_b])
        await session.commit()
        org_a_id = org_a.id
        org_b_id = org_b.id

    await db.disconnect()

    app = create_app(settings=settings)

    # Protected route requiring ORG_ADMIN role
    @app.get("/test/admin-only", dependencies=[Depends(require_role(Role.ORG_ADMIN))])
    async def admin_only() -> dict[str, str]:
        return {"status": "authorized"}

    # Protected route requiring TASK_CREATE permission
    @app.post("/test/tasks", dependencies=[Depends(require_permission(Permission.TASK_CREATE))])
    async def create_task() -> dict[str, str]:
        return {"status": "task_created"}

    yield app, org_a_id, org_b_id


class TestRBACRouteGuards:
    def test_require_role_admin_success(
        self,
        rbac_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _ = rbac_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, sub="sub-admin-a")

        with TestClient(app) as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json() == {"status": "authorized"}

    def test_require_role_insufficient_privilege_returns_403(
        self,
        rbac_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _ = rbac_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, sub="sub-member-a")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
            body = resp.json()
            assert body["code"] == "FORBIDDEN"
            assert "Minimum role required" in body["message"]

    def test_require_permission_member_can_create_task(
        self,
        rbac_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _ = rbac_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, sub="sub-member-a")

        with TestClient(app) as client:
            resp = client.post(
                "/test/tasks",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json() == {"status": "task_created"}

    def test_require_permission_viewer_cannot_create_task(
        self,
        rbac_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _ = rbac_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, sub="sub-viewer-a")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/test/tasks",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
            body = resp.json()
            assert body["code"] == "FORBIDDEN"
            assert "Missing required permission" in body["message"]
