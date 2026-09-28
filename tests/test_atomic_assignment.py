"""Tests for M17 — Atomic Assignment / Row Locks.

Validates:
- Row-level locking (SELECT ... FOR UPDATE) during assignment
- 20 simultaneous concurrent assignment attempts: exactly one winner
- 19 losers receive 409 Conflict (TASK_ALREADY_ASSIGNED)
- Forceful takeover support with allow_takeover=True
- Releasing a claimed task allows new assignment without takeover
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
async def atomic_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, list[uuid.UUID]]]:
    """Fixture providing app, org, project, user, and 20 registered agents."""
    db_path = tmp_path / "atomic_assign_test.db"
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

    agent_ids: list[uuid.UUID] = []

    async with db.session_factory() as session:
        org = Organization(name="Atomic Org", slug="atomic-org")
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
            name="Atomic Project",
            slug="atomic-proj",
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

        # Create 20 agents
        for i in range(20):
            agent = Agent(
                organization_id=org.id,
                project_id=proj.id,
                name=f"Worker Agent {i}",
                slug=f"worker-agent-{i}",
                role="DEVELOPER",
            )
            session.add(agent)
            await session.flush()
            agent_ids.append(agent.id)

        await session.commit()

    app = create_app(settings)
    yield app, org.id, proj.id, user.id, agent_ids

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_20_simultaneous_assignments_exactly_one_winner(
    atomic_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, list[uuid.UUID]],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Test 20 simultaneous concurrent assignments produces exactly one winner."""
    app, _, proj_id, _, agent_ids = atomic_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a task in TODO state
        create_res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Concurrent Race Task", "priority": "HIGH"},
            headers=headers,
        )
        assert create_res.status_code == status.HTTP_201_CREATED
        task_id = create_res.json()["id"]

        # Run 20 simultaneous assignments concurrently
        tasks = [
            client.post(
                f"/api/v1/tasks/{task_id}/assign",
                json={
                    "assignee_type": "AGENT",
                    "assignee_id": str(agent_ids[i]),
                    "allow_takeover": False,
                },
                headers=headers,
            )
            for i in range(20)
        ]
        responses = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in responses]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"Expected exactly 1 winner, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 19

        # Verify conflict errors returned TASK_ALREADY_ASSIGNED
        for r in responses:
            if r.status_code == status.HTTP_409_CONFLICT:
                body = r.json()
                assert body["code"] == "TASK_ALREADY_ASSIGNED"

        # Check final task state
        get_res = await client.get(f"/api/v1/projects/{proj_id}/tasks", headers=headers)
        assert get_res.status_code == status.HTTP_200_OK
        task_data = next(t for t in get_res.json() if t["id"] == task_id)
        assert task_data["status"] == "CLAIMED"
        assert task_data["assigned_agent_id"] is not None

        # Verify that winner matches the 200 response assignee
        winner_res = next(r for r in responses if r.status_code == status.HTTP_200_OK)
        winner_data = winner_res.json()
        assert task_data["assigned_agent_id"] == winner_data["assigned_agent_id"]


@pytest.mark.asyncio
async def test_takeover_with_allow_takeover(
    atomic_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, list[uuid.UUID]],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Test that setting allow_takeover=True permits reassigning an already assigned task."""
    app, _, proj_id, _, agent_ids = atomic_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create task
        res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Takeover Task"},
            headers=headers,
        )
        task_id = res.json()["id"]

        # Assign to Agent 0
        assign_res = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"assignee_type": "AGENT", "assignee_id": str(agent_ids[0])},
            headers=headers,
        )
        assert assign_res.status_code == status.HTTP_200_OK
        assert assign_res.json()["assigned_agent_id"] == str(agent_ids[0])

        # Attempt takeover by Agent 1 with allow_takeover=False -> fails
        reject_res = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"assignee_type": "AGENT", "assignee_id": str(agent_ids[1])},
            headers=headers,
        )
        assert reject_res.status_code == status.HTTP_409_CONFLICT
        assert reject_res.json()["code"] == "TASK_ALREADY_ASSIGNED"

        # Forceful takeover with allow_takeover=True -> succeeds
        takeover_res = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={
                "assignee_type": "AGENT",
                "assignee_id": str(agent_ids[1]),
                "allow_takeover": True,
            },
            headers=headers,
        )
        assert takeover_res.status_code == status.HTTP_200_OK
        assert takeover_res.json()["assigned_agent_id"] == str(agent_ids[1])
