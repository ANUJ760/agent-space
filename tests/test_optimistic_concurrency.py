"""Tests for M16 — Optimistic Concurrency Control (OCC).

Validates:
- Incremental version tracking across entity updates
- Stale client rejection with 409 TASK_VERSION_CONFLICT
- Atomic update pattern: UPDATE tasks SET ... WHERE id = :id AND version = :expected_version
- Recovery pattern: stale client refreshes and succeeds with current version
- Optimistic locking enforcement on state transitions
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
async def occ_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID]]:
    """Fixture providing app, org ID, and project ID."""
    db_path = tmp_path / "occ_test.db"
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
        org = Organization(name="OCC Org", slug="occ-org")
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
            name="OCC Project",
            slug="occ-project",
            created_by_id=user.id,
        )
        session.add(proj)
        await session.flush()

        pm = ProjectMember(
            project_id=proj.id,
            user_id=user.id,
            role="PROJECT_OWNER",
        )
        session.add(pm)
        await session.commit()

        org_id = org.id
        proj_id = proj.id

    await db.disconnect()

    app = create_app(settings)
    yield app, org_id, proj_id


class TestOptimisticConcurrency:
    """Test suite for optimistic concurrency control and stale write rejection."""

    def test_stale_client_patch_rejected_with_409(
        self,
        occ_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        """Simulate two concurrent clients modifying the same task."""
        app, _, proj_id = occ_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            # 1. Create a task (starts at version 1)
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Shared Resource Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]
            assert create_resp.json()["version"] == 1

            # 2. Both Client A and Client B read task at version 1
            read_task = client.get(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}
            ).json()
            initial_version = read_task["version"]
            assert initial_version == 1

            # 3. Client A writes first with expected_version = 1 -> succeeds, increments to 2
            resp_a = client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"title": "Client A Update", "expected_version": initial_version},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp_a.status_code == status.HTTP_200_OK
            assert resp_a.json()["version"] == 2
            assert resp_a.json()["title"] == "Client A Update"

            # 4. Client B (stale) attempts update with old expected_version = 1 -> BLOCKED with 409
            resp_b = client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"title": "Client B Stale Update", "expected_version": initial_version},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp_b.status_code == status.HTTP_409_CONFLICT
            assert resp_b.json()["code"] == "TASK_VERSION_CONFLICT"

            # 5. Client B recovers: reads latest state (version 2) and retries with expected_version = 2
            fresh_task = client.get(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}
            ).json()
            assert fresh_task["version"] == 2

            resp_b_retry = client.patch(
                f"/api/v1/tasks/{task_id}",
                json={
                    "title": "Client B Resolved Update",
                    "expected_version": fresh_task["version"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp_b_retry.status_code == status.HTTP_200_OK
            assert resp_b_retry.json()["version"] == 3
            assert resp_b_retry.json()["title"] == "Client B Resolved Update"

    def test_stale_transition_rejected_with_409(
        self,
        occ_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        """Verify optimistic lock on state transition endpoint."""
        app, _, proj_id = occ_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "State Transition OCC Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            # Advance task to CLAIMED (increments version to 2)
            client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"status": "CLAIMED"},
                headers={"Authorization": f"Bearer {token}"},
            )

            # Try to transition with stale expected_version = 1
            stale_trans = client.post(
                f"/api/v1/tasks/{task_id}/transition",
                json={"status": "IN_PROGRESS", "expected_version": 1},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert stale_trans.status_code == status.HTTP_409_CONFLICT
            assert stale_trans.json()["code"] == "TASK_VERSION_CONFLICT"
