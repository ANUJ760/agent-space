"""Tests for M13 — Task State Machine & Transition Rules.

Validates:
- Every allowed and forbidden transition between all TaskStatus states
- Self-transition identity (no-op)
- Exception handling and ConflictError raising
- Enforcement through generic PATCH /api/v1/tasks/{task_id}
- Enforcement through dedicated POST /api/v1/tasks/{task_id}/transition
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
from app.errors import ConflictError
from app.main import create_app
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.services.task_state_machine import (
    ALLOWED_TRANSITIONS,
    TaskStatus,
    check_transition_or_raise,
    validate_transition,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


class TestTaskStateMachineUnit:
    """Unit tests for state transition validation matrix."""

    def test_all_statuses_represented(self) -> None:
        expected = {
            "TODO",
            "CLAIMED",
            "IN_PROGRESS",
            "BLOCKED",
            "REVIEW",
            "DONE",
            "FAILED",
            "CANCELLED",
            "PAUSED",
        }
        actual = {s.value for s in TaskStatus}
        assert actual == expected

    def test_every_allowed_and_forbidden_transition(self) -> None:
        """Exhaustively verify every (current, target) combination."""
        for current in TaskStatus:
            allowed_for_current = ALLOWED_TRANSITIONS.get(current, set())
            for target in TaskStatus:
                is_valid = validate_transition(current, target)
                if current == target or target in allowed_for_current:
                    assert is_valid, f"Expected {current} -> {target} to be ALLOWED"
                    # check_transition_or_raise should not raise
                    check_transition_or_raise(current, target)
                else:
                    assert not is_valid, f"Expected {current} -> {target} to be FORBIDDEN"
                    with pytest.raises(ConflictError) as exc_info:
                        check_transition_or_raise(current, target)
                    assert exc_info.value.code == "INVALID_STATE_TRANSITION"

    def test_invalid_status_strings_return_false(self) -> None:
        assert not validate_transition("TODO", "NON_EXISTENT")
        assert not validate_transition("UNKNOWN", "DONE")


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
async def state_machine_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID]]:
    """Fixture providing app, org ID, and project ID."""
    db_path = tmp_path / "state_machine_test.db"
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
        org = Organization(name="Test Org", slug="test-org")
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
            name="Workflow Project",
            slug="workflow-project",
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


class TestTaskStateMachineAPI:
    """API integration tests verifying transition enforcement."""

    def test_generic_patch_blocks_illegal_transition(
        self,
        state_machine_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = state_machine_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            # Create task in TODO status
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "State Test Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]
            assert create_resp.json()["status"] == "TODO"

            # Attempt forbidden transition TODO -> DONE
            patch_resp = client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"status": "DONE"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert patch_resp.status_code == status.HTTP_409_CONFLICT
            assert patch_resp.json()["code"] == "INVALID_STATE_TRANSITION"

    def test_generic_patch_allows_legal_transition(
        self,
        state_machine_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = state_machine_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "State Test Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            # Legal transition: TODO -> IN_PROGRESS
            patch_resp = client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"status": "IN_PROGRESS"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert patch_resp.status_code == status.HTTP_200_OK
            assert patch_resp.json()["status"] == "IN_PROGRESS"

    def test_dedicated_transition_endpoint(
        self,
        state_machine_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = state_machine_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            create_resp = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Pipeline Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]

            # Legal transition via endpoint: TODO -> CLAIMED
            r1 = client.post(
                f"/api/v1/tasks/{task_id}/transition",
                json={"status": "CLAIMED", "reason": "Claimed by autonomous agent"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r1.status_code == status.HTTP_200_OK
            assert r1.json()["status"] == "CLAIMED"

            # CLAIMED -> IN_PROGRESS
            r2 = client.post(
                f"/api/v1/tasks/{task_id}/transition",
                json={"status": "IN_PROGRESS"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r2.status_code == status.HTTP_200_OK
            assert r2.json()["status"] == "IN_PROGRESS"

            # IN_PROGRESS -> REVIEW
            r3 = client.post(
                f"/api/v1/tasks/{task_id}/transition",
                json={"status": "REVIEW"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r3.status_code == status.HTTP_200_OK
            assert r3.json()["status"] == "REVIEW"

            # REVIEW -> DONE
            r4 = client.post(
                f"/api/v1/tasks/{task_id}/transition",
                json={"status": "DONE"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r4.status_code == status.HTTP_200_OK
            assert r4.json()["status"] == "DONE"

            # Illegal from DONE -> FAILED
            r5 = client.post(
                f"/api/v1/tasks/{task_id}/transition",
                json={"status": "FAILED"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r5.status_code == status.HTTP_409_CONFLICT
            assert r5.json()["code"] == "INVALID_STATE_TRANSITION"
