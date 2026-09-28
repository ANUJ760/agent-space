"""Tests for M14 — Task Dependencies & DAG Execution Guards.

Validates:
- Adding dependency edges
- Listing task dependencies
- Preventing self-dependencies (A -> A)
- Preventing immediate cycles (A -> B -> A)
- Preventing transitive multi-hop cycles (A -> B -> C -> A)
- Execution guard: preventing execution/claiming when prerequisites are incomplete
- Unlocking execution once all dependencies reach DONE
- Removing dependency edges
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
async def dep_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID]]:
    """Fixture providing app, org ID, and project ID."""
    db_path = tmp_path / "dep_test.db"
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
        org = Organization(name="DAG Org", slug="dag-org")
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
            name="DAG Project",
            slug="dag-project",
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


class TestTaskDependenciesAPI:
    """Test suite for task dependency DAG operations."""

    def test_add_and_list_dependency(
        self,
        dep_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = dep_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            # Create Task A and Task B
            r_a = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task A"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_b = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task B"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_a_id = r_a.json()["id"]
            task_b_id = r_b.json()["id"]

            # Task A depends on Task B
            add_resp = client.post(
                f"/api/v1/tasks/{task_a_id}/dependencies",
                json={"depends_on_task_id": task_b_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert add_resp.status_code == status.HTTP_201_CREATED
            assert add_resp.json()["task_id"] == task_a_id
            assert add_resp.json()["depends_on_task_id"] == task_b_id

            # List dependencies of Task A
            list_resp = client.get(
                f"/api/v1/tasks/{task_a_id}/dependencies",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert list_resp.status_code == status.HTTP_200_OK
            deps = list_resp.json()
            assert len(deps) == 1
            assert deps[0]["id"] == task_b_id

    def test_self_dependency_rejected(
        self,
        dep_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = dep_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            r_a = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task Self"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = r_a.json()["id"]

            resp = client.post(
                f"/api/v1/tasks/{task_id}/dependencies",
                json={"depends_on_task_id": task_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_immediate_cycle_rejected(
        self,
        dep_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = dep_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            r_a = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task A"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_b = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task B"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_a = r_a.json()["id"]
            task_b = r_b.json()["id"]

            # A -> B
            r1 = client.post(
                f"/api/v1/tasks/{task_a}/dependencies",
                json={"depends_on_task_id": task_b},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r1.status_code == status.HTTP_201_CREATED

            # Try B -> A (would create A -> B -> A)
            r2 = client.post(
                f"/api/v1/tasks/{task_b}/dependencies",
                json={"depends_on_task_id": task_a},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r2.status_code == status.HTTP_409_CONFLICT
            assert r2.json()["code"] == "CYCLIC_DEPENDENCY"

    def test_transitive_cycle_rejected(
        self,
        dep_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = dep_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            r_a = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "A"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_b = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "B"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_c = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "C"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_a = r_a.json()["id"]
            task_b = r_b.json()["id"]
            task_c = r_c.json()["id"]

            # A depends on B (A -> B)
            client.post(
                f"/api/v1/tasks/{task_a}/dependencies",
                json={"depends_on_task_id": task_b},
                headers={"Authorization": f"Bearer {token}"},
            )
            # B depends on C (B -> C)
            client.post(
                f"/api/v1/tasks/{task_b}/dependencies",
                json={"depends_on_task_id": task_c},
                headers={"Authorization": f"Bearer {token}"},
            )

            # Try C depends on A (C -> A -> B -> C cycle!)
            r_cycle = client.post(
                f"/api/v1/tasks/{task_c}/dependencies",
                json={"depends_on_task_id": task_a},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r_cycle.status_code == status.HTTP_409_CONFLICT
            assert r_cycle.json()["code"] == "CYCLIC_DEPENDENCY"

    def test_execution_guard_blocks_until_dependencies_done(
        self,
        dep_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = dep_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            r_a = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Deploy Service"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_b = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Pass Unit Tests"},
                headers={"Authorization": f"Bearer {token}"},
            )
            deploy_task_id = r_a.json()["id"]
            test_task_id = r_b.json()["id"]

            # Deploy Service depends on Pass Unit Tests
            client.post(
                f"/api/v1/tasks/{deploy_task_id}/dependencies",
                json={"depends_on_task_id": test_task_id},
                headers={"Authorization": f"Bearer {token}"},
            )

            # Try to start Deploy Service before tests pass -> blocked!
            start_resp = client.patch(
                f"/api/v1/tasks/{deploy_task_id}",
                json={"status": "IN_PROGRESS"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert start_resp.status_code == status.HTTP_409_CONFLICT
            assert start_resp.json()["code"] == "TASK_DEPENDENCIES_UNRESOLVED"

            # Now advance Pass Unit Tests to DONE (TODO -> IN_PROGRESS -> DONE)
            client.patch(
                f"/api/v1/tasks/{test_task_id}",
                json={"status": "IN_PROGRESS"},
                headers={"Authorization": f"Bearer {token}"},
            )
            client.patch(
                f"/api/v1/tasks/{test_task_id}",
                json={"status": "DONE"},
                headers={"Authorization": f"Bearer {token}"},
            )

            # Now Deploy Service CAN execute!
            start_resp2 = client.patch(
                f"/api/v1/tasks/{deploy_task_id}",
                json={"status": "IN_PROGRESS"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert start_resp2.status_code == status.HTTP_200_OK
            assert start_resp2.json()["status"] == "IN_PROGRESS"

    def test_remove_dependency(
        self,
        dep_app: tuple[FastAPI, uuid.UUID, uuid.UUID],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, proj_id = dep_app
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-admin-a")

        with TestClient(app) as client:
            r_a = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task A"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_b = client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Task B"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_a = r_a.json()["id"]
            task_b = r_b.json()["id"]

            client.post(
                f"/api/v1/tasks/{task_a}/dependencies",
                json={"depends_on_task_id": task_b},
                headers={"Authorization": f"Bearer {token}"},
            )

            # Delete dependency
            del_resp = client.delete(
                f"/api/v1/tasks/{task_a}/dependencies/{task_b}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert del_resp.status_code == status.HTTP_204_NO_CONTENT

            # Listing dependencies now returns empty
            list_resp = client.get(
                f"/api/v1/tasks/{task_a}/dependencies", headers={"Authorization": f"Bearer {token}"}
            )
            assert len(list_resp.json()) == 0
