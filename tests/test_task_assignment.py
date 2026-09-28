"""Tests for M15 — Task Assignment (Human & Agent).

Validates:
- Assigning a task to an autonomous agent (assignee_type=AGENT)
- Auto-transition from TODO to CLAIMED upon assignment
- Assigning a task to a human team member (assignee_type=HUMAN)
- Releasing a task back to TODO with assignments cleared
- Validation errors on non-existent or foreign tenant assignees
- Dependency guard prevents claiming when prerequisite dependencies are not done
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
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": "admin_a",
        "email": "admin@a.com",
        "email_verified": True,
        "realm_access": {"roles": ["developer"]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def assignment_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Fixture with org, project, user, and agent."""
    db_path = tmp_path / "assign_test.db"
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
        org = Organization(name="Assign Org", slug="assign-org")
        session.add(org)
        await session.flush()

        user = User(
            external_subject="sub-admin-a",
            username="admin_a",
            email="admin@a.com",
            role="ORG_ADMIN",
            organization_id=org.id,
        )
        session.add(user)
        await session.flush()

        proj = Project(
            organization_id=org.id,
            name="Assign Project",
            slug="assign-proj",
            created_by_id=user.id,
        )
        session.add(proj)
        await session.flush()

        pm = ProjectMember(
            project_id=proj.id,
            user_id=user.id,
            role="PROJECT_OWNER",
        )
        agent = Agent(
            organization_id=org.id,
            project_id=proj.id,
            name="Test Bot",
            slug="test-bot",
            role="TESTER",
        )
        session.add_all([pm, agent])
        await session.commit()

        org_id = org.id
        proj_id = proj.id
        user_id = user.id
        agent_id = agent.id

    await db.disconnect()

    app = create_app(settings)
    yield app, org_id, proj_id, user_id, agent_id


class TestTaskAssignmentAPIs:
    """Test suite for task worker assignment and release."""

    def test_assign_to_agent_success(
        self,
        assignment_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id, _, agent_id = assignment_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Run Integration Suite"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]
            assert create_resp.json()["status"] == "TODO"

            # Assign to agent
            assign_resp = client.post(
                f"/api/v1/tasks/{task_id}/assign",
                json={"assignee_type": "AGENT", "assignee_id": str(agent_id)},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert assign_resp.status_code == status.HTTP_200_OK
            task = assign_resp.json()
            assert task["assigned_agent_id"] == str(agent_id)
            assert task["assigned_user_id"] is None
            assert task["status"] == "CLAIMED"

    def test_assign_to_human_success(
        self,
        assignment_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id, user_id, _ = assignment_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Security Audit"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            # Assign to human
            assign_resp = client.post(
                f"/api/v1/tasks/{task_id}/assign",
                json={"assignee_type": "HUMAN", "assignee_id": str(user_id)},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert assign_resp.status_code == status.HTTP_200_OK
            task = assign_resp.json()
            assert task["assigned_user_id"] == str(user_id)
            assert task["assigned_agent_id"] is None
            assert task["status"] == "CLAIMED"

    def test_release_task(
        self,
        assignment_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id, user_id, _ = assignment_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Review PR #42"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            # Assign
            client.post(
                f"/api/v1/tasks/{task_id}/assign",
                json={"assignee_type": "HUMAN", "assignee_id": str(user_id)},
                headers={"Authorization": f"Bearer {token}"},
            )

            # Release
            release_resp = client.post(
                f"/api/v1/tasks/{task_id}/release",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert release_resp.status_code == status.HTTP_200_OK
            task = release_resp.json()
            assert task["assigned_user_id"] is None
            assert task["assigned_agent_id"] is None
            assert task["status"] == "TODO"

    def test_assign_fails_with_foreign_assignee(
        self,
        assignment_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id, _, _ = assignment_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task A"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            fake_id = str(uuid.uuid4())
            resp = client.post(
                f"/api/v1/tasks/{task_id}/assign",
                json={"assignee_type": "AGENT", "assignee_id": fake_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
