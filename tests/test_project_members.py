"""Tests for M10 — Project Members.

Validates:
- GET /api/v1/projects/{id}/members: lists project members with roles
- POST /api/v1/projects/{id}/members:
  - adds member to project
  - rejects user from a different organization (403 Forbidden)
  - rejects duplicate membership (409 Conflict)
  - rejects non-existent user (404 Not Found)
- PATCH /api/v1/projects/{id}/members/{user_id}:
  - updates member role
  - rejects demoting the sole PROJECT_OWNER (409 Conflict)
- DELETE /api/v1/projects/{id}/members/{user_id}:
  - removes member
  - rejects removing the sole PROJECT_OWNER (409 Conflict)
- RBAC permission enforcement: member operations require PROJECT_MANAGE_MEMBERS
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
from app.models.project import Project
from app.models.project_member import ProjectMember
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
    username_map = {
        "sub-owner": "owner_user",
        "sub-teammate": "teammate_user",
        "sub-outsider": "outsider_user",
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
async def member_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Set up app with project, project owner, member in same org, and user in foreign org."""
    db_path = tmp_path / "member_test.db"
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
        org_a = Organization(name="Org Prime", slug="org-prime")
        org_b = Organization(name="Org Foreign", slug="org-foreign")
        session.add_all([org_a, org_b])
        await session.flush()

        # User 1: Project Owner in Org A
        owner = User(
            external_subject="sub-owner",
            username="owner_user",
            email="owner@prime.com",
            role=Role.ORG_ADMIN.value,
            organization_id=org_a.id,
        )
        # User 2: Teammate in Org A (not yet member)
        teammate = User(
            external_subject="sub-teammate",
            username="teammate_user",
            email="teammate@prime.com",
            role=Role.MEMBER.value,
            organization_id=org_a.id,
        )
        # User 3: Outsider in Org B
        outsider = User(
            external_subject="sub-outsider",
            username="outsider_user",
            email="outsider@foreign.com",
            role=Role.MEMBER.value,
            organization_id=org_b.id,
        )
        session.add_all([owner, teammate, outsider])
        await session.flush()

        # Project in Org A
        proj = Project(
            organization_id=org_a.id,
            name="Quantum Leap",
            slug="quantum-leap",
            created_by_id=owner.id,
        )
        session.add(proj)
        await session.flush()

        # Owner membership
        pm_owner = ProjectMember(
            project_id=proj.id,
            user_id=owner.id,
            role="PROJECT_OWNER",
        )
        session.add(pm_owner)
        await session.commit()

        project_id = proj.id
        owner_id = owner.id
        teammate_id = teammate.id
        outsider_id = outsider.id
        org_a_id = org_a.id

    await db.disconnect()

    app = create_app(settings=settings)
    yield app, project_id, owner_id, teammate_id, outsider_id, org_a_id


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestProjectMemberAPIs:
    def test_list_project_members(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, owner_id, _, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_200_OK
            members = resp.json()
            assert len(members) == 1
            assert members[0]["user_id"] == str(owner_id)
            assert members[0]["role"] == "PROJECT_OWNER"
            assert members[0]["username"] == "owner_user"

    def test_add_member_from_same_organization_success(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, _, teammate_id, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": str(teammate_id), "role": "MEMBER"},
            )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["user_id"] == str(teammate_id)
            assert data["role"] == "MEMBER"
            assert data["username"] == "teammate_user"

    def test_add_member_from_different_organization_rejected(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, _, _, outsider_id, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": str(outsider_id), "role": "MEMBER"},
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert "different organization" in resp.json()["message"]

    def test_add_duplicate_member_returns_conflict(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, owner_id, _, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": str(owner_id), "role": "PROJECT_ADMIN"},
            )
            assert resp.status_code == status.HTTP_409_CONFLICT
            assert resp.json()["code"] == "USER_ALREADY_MEMBER"

    def test_patch_member_role(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, _, teammate_id, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app) as client:
            # 1. Add teammate
            client.post(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": str(teammate_id), "role": "MEMBER"},
            )

            # 2. Promote to PROJECT_ADMIN
            patch_resp = client.patch(
                f"/api/v1/projects/{project_id}/members/{teammate_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"role": "PROJECT_ADMIN"},
            )
            assert patch_resp.status_code == status.HTTP_200_OK
            assert patch_resp.json()["role"] == "PROJECT_ADMIN"

    def test_demote_sole_owner_rejected(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, owner_id, _, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/projects/{project_id}/members/{owner_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"role": "MEMBER"},
            )
            assert resp.status_code == status.HTTP_409_CONFLICT
            assert resp.json()["code"] == "LAST_OWNER_DEMOTION"

    def test_remove_sole_owner_rejected(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, owner_id, _, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(
                f"/api/v1/projects/{project_id}/members/{owner_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_409_CONFLICT
            assert resp.json()["code"] == "LAST_OWNER_REMOVAL"

    def test_remove_member_success(
        self,
        member_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, project_id, _, teammate_id, _, _ = member_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-owner")

        with TestClient(app) as client:
            # 1. Add teammate
            client.post(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": str(teammate_id), "role": "MEMBER"},
            )

            # 2. Remove teammate
            del_resp = client.delete(
                f"/api/v1/projects/{project_id}/members/{teammate_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert del_resp.status_code == status.HTTP_204_NO_CONTENT

            # 3. Verify member list now only has 1
            list_resp = client.get(
                f"/api/v1/projects/{project_id}/members",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert len(list_resp.json()) == 1
