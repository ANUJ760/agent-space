"""Tests for M09 — Projects.

Validates:
- POST /api/v1/projects: create project with automatic PROJECT_OWNER assignment
- Organization-scoped project queries and cross-tenant isolation
- Slug uniqueness enforcement per organization (same slug allowed across different orgs)
- GET /api/v1/projects: lists only caller's organization projects
- GET /api/v1/projects/{id}: retrieves project, rejects cross-organization access (403)
- PATCH /api/v1/projects/{id}: updates metadata and increments optimistic version
- DELETE /api/v1/projects/{id}: deletes project with cascade
- GET /api/v1/projects/{id}/summary: returns executive project metrics
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.auth import OIDCClient, Role, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager
from app.main import create_app
from app.models.organization import Organization
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


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


def sign_token(pem_priv: bytes, sub: str) -> str:
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": sub,
        "email": f"{sub}@example.com",
        "email_verified": True,
        "realm_access": {"roles": ["developer"]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def project_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Set up app with 2 organizations (Org A, Org B) and users."""
    db_path = tmp_path / "project_test.db"
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
        org_a = Organization(name="Org Alpha", slug="org-alpha")
        org_b = Organization(name="Org Beta", slug="org-beta")
        session.add_all([org_a, org_b])
        await session.flush()

        user_a = User(
            external_subject="sub-user-a",
            username="user_a",
            email="user_a@alpha.com",
            role=Role.ORG_ADMIN.value,
            organization_id=org_a.id,
        )
        user_b = User(
            external_subject="sub-user-b",
            username="user_b",
            email="user_b@beta.com",
            role=Role.ORG_ADMIN.value,
            organization_id=org_b.id,
        )
        session.add_all([user_a, user_b])
        await session.commit()

        org_a_id = org_a.id
        org_b_id = org_b.id
        user_a_id = user_a.id
        user_b_id = user_b.id

    await db.disconnect()

    app = create_app(settings=settings)
    yield app, org_a_id, org_b_id, user_a_id, user_b_id


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestProjectAPIs:
    def test_create_project_success(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, org_a_id, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-user-a")

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "Apollo Mission",
                    "slug": "apollo-mission",
                    "description": "Lunar exploration program",
                    "default_branch": "main",
                },
            )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["name"] == "Apollo Mission"
            assert data["slug"] == "apollo-mission"
            assert data["organization_id"] == str(org_a_id)
            assert data["version"] == 1

    def test_create_project_slug_conflict_in_same_organization(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-user-a")

        with TestClient(app) as client:
            # First creation
            client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Project One", "slug": "project-shared-slug"},
            )

            # Duplicate slug in same organization
            dup = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Project One Duplicate", "slug": "project-shared-slug"},
            )
            assert dup.status_code == status.HTTP_409_CONFLICT
            assert dup.json()["code"] == "PROJECT_SLUG_CONFLICT"

    def test_same_slug_allowed_in_different_organizations(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-user-a")
        token_b = sign_token(pem_priv, "sub-user-b")

        with TestClient(app) as client:
            # Org A creates slug
            resp_a = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "Shared Name", "slug": "shared-slug"},
            )
            assert resp_a.status_code == status.HTTP_201_CREATED

            # Org B creates same slug
            resp_b = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_b}"},
                json={"name": "Shared Name", "slug": "shared-slug"},
            )
            assert resp_b.status_code == status.HTTP_201_CREATED

    def test_list_projects_strictly_organization_scoped(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-user-a")
        token_b = sign_token(pem_priv, "sub-user-b")

        with TestClient(app) as client:
            # Create project in Org A
            client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "Project Alpha", "slug": "project-alpha"},
            )
            # Create project in Org B
            client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_b}"},
                json={"name": "Project Beta", "slug": "project-beta"},
            )

            # User A listing
            list_a = client.get(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert list_a.status_code == status.HTTP_200_OK
            slugs_a = [p["slug"] for p in list_a.json()]
            assert "project-alpha" in slugs_a
            assert "project-beta" not in slugs_a

    def test_get_project_cross_organization_denied(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-user-a")
        token_b = sign_token(pem_priv, "sub-user-b")

        with TestClient(app, raise_server_exceptions=False) as client:
            # User A creates project
            created = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "Secret Project", "slug": "secret-project"},
            ).json()
            proj_id = created["id"]

            # User B attempts to access User A's project
            resp = client.get(
                f"/api/v1/projects/{proj_id}",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert resp.json()["code"] == "FORBIDDEN"

    def test_patch_project_updates_fields_and_version(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-user-a")

        with TestClient(app) as client:
            created = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "Initial Name", "slug": "patch-test"},
            ).json()
            proj_id = created["id"]
            assert created["version"] == 1

            patch_resp = client.patch(
                f"/api/v1/projects/{proj_id}",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "Updated Name", "description": "New description"},
            )
            assert patch_resp.status_code == status.HTTP_200_OK
            updated = patch_resp.json()
            assert updated["name"] == "Updated Name"
            assert updated["description"] == "New description"
            assert updated["version"] == 2

    def test_delete_project_success(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-user-a")

        with TestClient(app) as client:
            created = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "To Delete", "slug": "to-delete"},
            ).json()
            proj_id = created["id"]

            del_resp = client.delete(
                f"/api/v1/projects/{proj_id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert del_resp.status_code == status.HTTP_204_NO_CONTENT

            # Verify 404 after deletion
            get_resp = client.get(
                f"/api/v1/projects/{proj_id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert get_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_project_summary_endpoint(
        self,
        project_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, _, _ = project_app
        _, _, pem_priv, _ = rsa_keys
        token_a = sign_token(pem_priv, "sub-user-a")

        with TestClient(app) as client:
            created = client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "Summary Target", "slug": "summary-target"},
            ).json()
            proj_id = created["id"]

            summary_resp = client.get(
                f"/api/v1/projects/{proj_id}/summary",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert summary_resp.status_code == status.HTTP_200_OK
            summary = summary_resp.json()
            assert summary["project"]["id"] == proj_id
            # Creator is automatically 1 member (PROJECT_OWNER)
            assert summary["member_count"] == 1
            assert summary["status"] == "ACTIVE"
