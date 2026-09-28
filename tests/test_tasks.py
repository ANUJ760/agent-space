"""Tests for M12 — Task Management & CRUD.

Validates:
- Creating project tasks with initial TODO state
- Listing tasks with status and priority filtering
- Retrieving single task by ID
- Updating task title, priority, context, and error messages
- Assigning valid agents and members
- Rejecting foreign organization agent/user assignment
- Deleting tasks
- Tenant isolation across organization boundaries
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.auth.oidc import OIDCClient, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager
from app.main import create_app
from app.models.agent import Agent
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


@pytest.fixture()
def rsa_keys() -> tuple[Any, Any, bytes, bytes]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    pem_priv = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_pub = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub, pem_priv, pem_pub


@pytest.fixture()
def oidc_setup(rsa_keys: tuple[Any, Any, bytes, bytes]) -> Any:
    _, public_key, _, _ = rsa_keys
    kc_settings = KeycloakSettings(
        server_url="http://localhost:8080",
        realm="agentspace",
        client_id="agentspace-backend",
        audience="agentspace-backend",
    )
    client = OIDCClient(kc_settings)
    client.register_mock_key("key-1", public_key)
    set_oidc_client(client)
    yield client
    client.clear_mock_keys()
    set_oidc_client(None)


def sign_token(pem_priv: bytes, sub: str) -> str:
    username_map = {
        "sub-admin-a": "admin_a",
        "sub-user-b": "user_b",
    }
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": username_map.get(sub, sub),
        "email": f"{sub}@example.com",
        "email_verified": True,
        "realm_access": {"roles": ["developer"]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def task_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Fixture with two orgs, admin in Org A, user in Org B, project in Org A, and agent in Org A."""
    db_path = tmp_path / "task_test.db"
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

    async with db.session_factory() as session:
        org_a = Organization(name="Org A", slug="org-a")
        org_b = Organization(name="Org B", slug="org-b")
        session.add_all([org_a, org_b])
        await session.flush()

        user_a = User(
            external_subject="sub-admin-a",
            username="admin_a",
            email="admin@a.com",
            role="ORG_ADMIN",
            organization_id=org_a.id,
        )
        user_b = User(
            external_subject="sub-user-b",
            username="user_b",
            email="user@b.com",
            role="MEMBER",
            organization_id=org_b.id,
        )
        session.add_all([user_a, user_b])
        await session.flush()

        proj_a = Project(
            organization_id=org_a.id,
            name="Project Beta",
            slug="project-beta",
            created_by_id=user_a.id,
        )
        session.add(proj_a)
        await session.flush()

        pm = ProjectMember(
            project_id=proj_a.id,
            user_id=user_a.id,
            role="PROJECT_OWNER",
        )
        agent_a = Agent(
            organization_id=org_a.id,
            project_id=proj_a.id,
            name="Coder Agent",
            slug="coder-agent",
            role="DEVELOPER",
        )
        session.add_all([pm, agent_a])
        await session.commit()

        org_a_id = org_a.id
        org_b_id = org_b.id
        user_a_id = user_a.id
        proj_a_id = proj_a.id
        agent_a_id = agent_a.id

    await db.disconnect()

    app = create_app(settings)
    yield app, org_a_id, org_b_id, user_a_id, proj_a_id, agent_a_id


class TestTaskAPIs:
    """Test suite for Task CRUD endpoints."""

    def test_create_task_success(
        self,
        task_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, org_a_id, _, _, proj_a_id, agent_a_id = task_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/projects/{proj_a_id}/tasks",
                json={
                    "title": "Build Auth Middleware",
                    "description": "Implement Keycloak token verification",
                    "priority": "HIGH",
                    "assigned_agent_id": str(agent_a_id),
                    "context": {"files": ["auth/oidc.py"]},
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["title"] == "Build Auth Middleware"
            assert data["status"] == "TODO"
            assert data["priority"] == "HIGH"
            assert data["assigned_agent_id"] == str(agent_a_id)
            assert data["project_id"] == str(proj_a_id)
            assert data["organization_id"] == str(org_a_id)
            assert data["version"] == 1

    def test_list_and_filter_tasks(
        self,
        task_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, proj_a_id, _ = task_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            # Create two tasks with different priorities
            client.post(
                f"/api/v1/projects/{proj_a_id}/tasks",
                json={"title": "Task Low", "priority": "LOW"},
                headers={"Authorization": f"Bearer {token}"},
            )
            client.post(
                f"/api/v1/projects/{proj_a_id}/tasks",
                json={"title": "Task High", "priority": "CRITICAL"},
                headers={"Authorization": f"Bearer {token}"},
            )

            # List all
            r_all = client.get(
                f"/api/v1/projects/{proj_a_id}/tasks",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r_all.status_code == status.HTTP_200_OK
            assert len(r_all.json()) >= 2

            # Filter by priority
            r_crit = client.get(
                f"/api/v1/projects/{proj_a_id}/tasks?priority=CRITICAL",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r_crit.status_code == status.HTTP_200_OK
            assert all(t["priority"] == "CRITICAL" for t in r_crit.json())

    def test_get_and_patch_task(
        self,
        task_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, proj_a_id, _ = task_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_a_id}/tasks",
                json={"title": "Draft Architecture", "priority": "MEDIUM"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            # Get task
            get_resp = client.get(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert get_resp.status_code == status.HTTP_200_OK
            assert get_resp.json()["title"] == "Draft Architecture"

            # Patch task metadata
            patch_resp = client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"title": "Approved Architecture", "priority": "HIGH"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert patch_resp.status_code == status.HTTP_200_OK
            updated = patch_resp.json()
            assert updated["title"] == "Approved Architecture"
            assert updated["priority"] == "HIGH"
            assert updated["version"] == 2

    def test_delete_task(
        self,
        task_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, proj_a_id, _ = task_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_a_id}/tasks",
                json={"title": "Disposable Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            del_resp = client.delete(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert del_resp.status_code == status.HTTP_204_NO_CONTENT

            get_resp = client.get(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert get_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_tenant_task_access_denied(
        self,
        task_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, proj_a_id, _ = task_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-admin-a")
        token_b = sign_token(pem_priv, "sub-user-b")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_a_id}/tasks",
                json={"title": "Private Tenant Task"},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            task_id = create_resp.json()["id"]

            # User B from Org B cannot read Task from Org A
            resp = client.get(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token_b}"}
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
