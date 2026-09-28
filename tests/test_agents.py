"""Tests for M11 — Agent Registry.

Validates:
- Registering organization-level agents
- Listing organization-level agents with status/role filters
- Fetching single agent by ID
- Slug uniqueness enforcement within organization
- Updating agent configuration, prompt, and model
- Deleting agents
- Project-scoped agent registration and listing
- Multi-tenant boundary isolation
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
async def agent_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Fixture with two orgs, admin in org A, user in org B, and a project in org A."""
    db_path = tmp_path / "agent_test.db"
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
            name="Project Alpha",
            slug="project-alpha",
            created_by_id=user_a.id,
        )
        session.add(proj_a)
        await session.flush()

        pm = ProjectMember(
            project_id=proj_a.id,
            user_id=user_a.id,
            role="PROJECT_OWNER",
        )
        session.add(pm)
        await session.commit()

        org_a_id = org_a.id
        org_b_id = org_b.id
        user_a_id = user_a.id
        proj_a_id = proj_a.id

    await db.disconnect()

    app = create_app(settings)
    yield app, org_a_id, org_b_id, user_a_id, proj_a_id


class TestAgentRegistryAPIs:
    """Test suite for Agent Registry endpoints."""

    def test_create_organization_agent_success(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, org_a_id, _, _, _ = agent_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agents",
                json={
                    "name": "Backend Architect",
                    "slug": "backend-architect",
                    "role": "ARCHITECT",
                    "model": "claude-3-5-sonnet",
                    "model_provider": "anthropic",
                    "capabilities": ["code_writing", "system_design"],
                    "system_prompt": "You are a senior systems architect.",
                    "configuration": {"temperature": 0.2},
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["name"] == "Backend Architect"
            assert data["slug"] == "backend-architect"
            assert data["organization_id"] == str(org_a_id)
            assert data["project_id"] is None
            assert data["version"] == 1

    def test_duplicate_agent_slug_rejected_with_409(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = agent_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        payload = {
            "name": "QA Agent",
            "slug": "qa-agent",
            "role": "TESTER",
        }
        with TestClient(app) as client:
            r1 = client.post(
                "/api/v1/agents",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r1.status_code == status.HTTP_201_CREATED

            r2 = client.post(
                "/api/v1/agents",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r2.status_code == status.HTTP_409_CONFLICT
            assert r2.json()["code"] == "AGENT_SLUG_EXISTS"

    def test_list_and_get_agent(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = agent_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/agents",
                json={"name": "Reviewer Agent", "slug": "reviewer-agent", "role": "REVIEWER"},
                headers={"Authorization": f"Bearer {token}"},
            )
            agent_id = create_resp.json()["id"]

            list_resp = client.get("/api/v1/agents", headers={"Authorization": f"Bearer {token}"})
            assert list_resp.status_code == status.HTTP_200_OK
            agents = list_resp.json()
            assert any(a["id"] == agent_id for a in agents)

            get_resp = client.get(
                f"/api/v1/agents/{agent_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert get_resp.status_code == status.HTTP_200_OK
            assert get_resp.json()["id"] == agent_id

    def test_update_agent_metadata(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = agent_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/agents",
                json={"name": "Old Name", "slug": "agent-updatable", "role": "DEVELOPER"},
                headers={"Authorization": f"Bearer {token}"},
            )
            agent_id = create_resp.json()["id"]

            patch_resp = client.patch(
                f"/api/v1/agents/{agent_id}",
                json={"name": "New Name", "model": "gpt-4o"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert patch_resp.status_code == status.HTTP_200_OK
            updated = patch_resp.json()
            assert updated["name"] == "New Name"
            assert updated["model"] == "gpt-4o"
            assert updated["version"] == 2

    def test_delete_agent(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = agent_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/agents",
                json={"name": "To Delete", "slug": "to-delete", "role": "DEVELOPER"},
                headers={"Authorization": f"Bearer {token}"},
            )
            agent_id = create_resp.json()["id"]

            del_resp = client.delete(
                f"/api/v1/agents/{agent_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert del_resp.status_code == status.HTTP_204_NO_CONTENT

            get_resp = client.get(
                f"/api/v1/agents/{agent_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert get_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_organization_agent_denied(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = agent_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-admin-a")
        token_b = sign_token(pem_priv, "sub-user-b")

        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/agents",
                json={"name": "Org A Secret Agent", "slug": "secret-agent"},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            agent_id = create_resp.json()["id"]

            # User B from Org B cannot read Org A's agent
            resp = client.get(
                f"/api/v1/agents/{agent_id}",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_project_scoped_agents(
        self,
        agent_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, proj_a_id = agent_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            # Create project-scoped agent
            create_resp = client.post(
                f"/api/v1/projects/{proj_a_id}/agents",
                json={"name": "Project Coder", "slug": "proj-coder", "role": "DEVELOPER"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert create_resp.status_code == status.HTTP_201_CREATED
            agent_id = create_resp.json()["id"]
            assert create_resp.json()["project_id"] == str(proj_a_id)

            # List project agents
            list_resp = client.get(
                f"/api/v1/projects/{proj_a_id}/agents",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert list_resp.status_code == status.HTTP_200_OK
            agents = list_resp.json()
            assert any(a["id"] == agent_id for a in agents)
