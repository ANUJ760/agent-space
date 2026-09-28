"""Tests for M18 — Idempotency.

Validates:
- Idempotency-Key header on mutating operations
- Same key + same request: returns original response (Idempotent-Replayed: true)
- Same key + different request: 409 Conflict (IDEMPOTENCY_KEY_REUSED)
- Duplicate concurrent requests: all succeed with the same original response
- Applicable across task creation, assignment, and status transitions
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from app.auth.oidc import OIDCClient, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager, set_db_manager
from app.main import create_app
from app.models.agent import Agent
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status


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
async def idemp_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Fixture with org, project, user, and agent."""
    db_path = tmp_path / "idemp_test.db"
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
    set_db_manager(db)

    async with db.session_factory() as session:
        org = Organization(name="Idemp Org", slug="idemp-org")
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
            name="Idemp Project",
            slug="idemp-proj",
            created_by_id=user.id,
        )
        session.add(proj)
        await session.flush()

        member = ProjectMember(
            project_id=proj.id,
            user_id=user.id,
            role="OWNER",
        )
        session.add(member)

        agent = Agent(
            organization_id=org.id,
            project_id=proj.id,
            name="Idemp Agent",
            slug="idemp-agent",
            role="DEVELOPER",
        )
        session.add(agent)
        await session.flush()

        await session.commit()

    app = create_app(settings)
    yield app, org.id, proj.id, user.id, agent.id

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_idempotent_task_creation_same_key_same_payload(
    idemp_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Same Idempotency-Key with same payload returns cached response without duplicate creation."""
    app, _, proj_id, _, _ = idemp_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    key = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": key}
    payload = {"title": "Idempotent Task", "priority": "HIGH"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First request
        res1 = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json=payload,
            headers=headers,
        )
        assert res1.status_code == status.HTTP_201_CREATED
        task1 = res1.json()
        assert res1.headers.get("Idempotent-Replayed") == "false"

        # Second request with exact same key and payload
        res2 = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json=payload,
            headers=headers,
        )
        assert res2.status_code == status.HTTP_201_CREATED
        task2 = res2.json()
        assert res2.headers.get("Idempotent-Replayed") == "true"
        assert task1["id"] == task2["id"]
        assert task1["title"] == task2["title"]

        # Verify only 1 task in database
        list_res = await client.get(f"/api/v1/projects/{proj_id}/tasks", headers=headers)
        assert list_res.status_code == status.HTTP_200_OK
        assert len(list_res.json()) == 1


@pytest.mark.asyncio
async def test_idempotent_key_reused_with_different_payload(
    idemp_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Same Idempotency-Key with a different payload returns 409 IDEMPOTENCY_KEY_REUSED."""
    app, _, proj_id, _, _ = idemp_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    key = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": key}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First request
        res1 = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Task A"},
            headers=headers,
        )
        assert res1.status_code == status.HTTP_201_CREATED

        # Second request with same key but different payload
        res2 = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Task B with different body"},
            headers=headers,
        )
        assert res2.status_code == status.HTTP_409_CONFLICT
        body = res2.json()
        assert body["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_with_same_key(
    idemp_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Multiple concurrent requests with same key and payload all succeed with original response."""
    app, _, proj_id, _, _ = idemp_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    key = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": key}
    payload = {"title": "Concurrent Idempotent Task"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Fire 10 concurrent requests with the exact same key and payload
        requests = [
            client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json=payload,
                headers=headers,
            )
            for _ in range(10)
        ]
        responses = await asyncio.gather(*requests)

        # All 10 must succeed with 201
        for r in responses:
            assert r.status_code == status.HTTP_201_CREATED

        # All 10 must return the identical task ID
        task_ids = {r.json()["id"] for r in responses}
        assert len(task_ids) == 1

        # Exactly 1 in database
        list_res = await client.get(f"/api/v1/projects/{proj_id}/tasks", headers=headers)
        assert list_res.status_code == status.HTTP_200_OK
        assert len(list_res.json()) == 1


@pytest.mark.asyncio
async def test_idempotent_task_assignment(
    idemp_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Idempotency works for assignment mutations."""
    app, _, proj_id, _, agent_id = idemp_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create task
        create_res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Assignment Idemp Task"},
            headers=headers,
        )
        task_id = create_res.json()["id"]

        # Assign with idempotency key
        key = str(uuid.uuid4())
        assign_headers = {**headers, "Idempotency-Key": key}
        assign_payload = {"assignee_type": "AGENT", "assignee_id": str(agent_id)}

        res1 = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json=assign_payload,
            headers=assign_headers,
        )
        assert res1.status_code == status.HTTP_200_OK
        assert res1.headers.get("Idempotent-Replayed") == "false"

        # Replay same assignment
        res2 = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json=assign_payload,
            headers=assign_headers,
        )
        assert res2.status_code == status.HTTP_200_OK
        assert res2.headers.get("Idempotent-Replayed") == "true"
        assert res2.json()["assigned_agent_id"] == str(agent_id)
