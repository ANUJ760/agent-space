"""Unit and concurrency tests for M53 (Human Takeover) and M54 (Human Handoff).

Validates:
- Atomic human takeover of an agent's task.
- Mandatory race test: two simultaneous takeovers -> exactly 1 succeeds, 1 receives 409 TAKEOVER_CONFLICT.
- Audit outbox event publication on takeover.
- Human to agent handoff with resumption instructions.
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


@pytest.fixture
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


@pytest.fixture
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
    return client


def sign_token(pem_priv: bytes, sub: str, roles: list[str] | None = None) -> str:
    headers = {"kid": "key-1", "alg": "RS256"}
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": sub,
        "email": f"{sub}@example.com",
        "email_verified": True,
        "realm_access": {"roles": roles or ["developer"]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers=headers)


@pytest.fixture
async def takeover_app(
    tmp_path: Path,
    oidc_setup: Any,
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    db_file = tmp_path / "takeover_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    settings = Settings(
        database_url=db_url,
        environment="test",
        debug=True,
        log_format="text",
    )
    db = DatabaseManager(settings.database)
    await db.connect()
    await db.create_all()
    set_db_manager(db)

    async with db.session_factory() as session:
        org = Organization(name="Takeover Org", slug="takeover-org")
        session.add(org)
        await session.flush()

        u1 = User(
            organization_id=org.id,
            external_subject="sub-alice",
            username="alice",
            email="alice@example.com",
            role="ORG_ADMIN",
        )
        u2 = User(
            organization_id=org.id,
            external_subject="sub-bob",
            username="bob",
            email="bob@example.com",
            role="ORG_ADMIN",
        )
        session.add_all([u1, u2])
        await session.flush()

        project = Project(
            organization_id=org.id,
            name="Takeover Project",
            slug="takeover-proj",
            created_by_id=u1.id,
        )
        session.add(project)
        await session.flush()

        pm1 = ProjectMember(project_id=project.id, user_id=u1.id, role="OWNER")
        pm2 = ProjectMember(project_id=project.id, user_id=u2.id, role="OWNER")
        session.add_all([pm1, pm2])

        ag = Agent(
            organization_id=org.id,
            project_id=project.id,
            name="Coding Bot",
            slug="coding-bot",
            role="DEVELOPER",
            system_prompt="You code.",
        )
        session.add(ag)
        await session.commit()

        org_id = org.id
        proj_id = project.id
        user1_id = u1.id
        user2_id = u2.id
        agent_id = ag.id

    app = create_app(settings)
    yield app, org_id, proj_id, user1_id, user2_id, agent_id
    await db.disconnect()


@pytest.mark.asyncio
async def test_human_takeover_and_handoff_lifecycle(
    takeover_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    app, _, proj_id, user1_id, _, agent_id = takeover_app
    _, _, pem_priv, _ = rsa_keys
    token_alice = sign_token(pem_priv, "sub-alice")
    headers_alice = {"Authorization": f"Bearer {token_alice}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create task
        create_res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Fix Critical Bug"},
            headers=headers_alice,
        )
        assert create_res.status_code == status.HTTP_201_CREATED
        task_id = create_res.json()["id"]

        # 2. Assign to Agent
        assign_res = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"assignee_type": "AGENT", "assignee_id": str(agent_id)},
            headers=headers_alice,
        )
        assert assign_res.status_code == status.HTTP_200_OK
        assert assign_res.json()["assigned_agent_id"] == str(agent_id)
        assert assign_res.json()["assigned_user_id"] is None

        # 3. Human Takeover by Alice
        takeover_res = await client.post(
            f"/api/v1/tasks/{task_id}/takeover",
            json={"reason": "Agent encountered unexpected exception"},
            headers=headers_alice,
        )
        assert takeover_res.status_code == status.HTTP_200_OK
        data = takeover_res.json()
        assert data["assigned_user_id"] == str(user1_id)
        assert data["assigned_agent_id"] is None
        assert data["status"] == "IN_PROGRESS"

        # 4. Verify audit event recorded
        audit_res = await client.get(
            f"/api/v1/projects/{proj_id}/audit-events", headers=headers_alice
        )
        assert audit_res.status_code == status.HTTP_200_OK
        events = audit_res.json()
        takeover_events = [e for e in events if e["event_type"] == "task.takeover"]
        assert len(takeover_events) == 1
        assert takeover_events[0]["payload"]["reason"] == "Agent encountered unexpected exception"

        # 5. Handoff back to Agent with instructions (M54)
        handoff_res = await client.post(
            f"/api/v1/tasks/{task_id}/handoff",
            json={
                "agent_id": str(agent_id),
                "instructions": "Added test cases in tests/test_auth.py. Please implement fix.",
            },
            headers=headers_alice,
        )
        assert handoff_res.status_code == status.HTTP_200_OK
        h_data = handoff_res.json()
        assert h_data["assigned_agent_id"] == str(agent_id)
        assert h_data["assigned_user_id"] is None
        assert h_data["status"] == "CLAIMED"
        assert (
            h_data["context"]["handoff_instructions"]
            == "Added test cases in tests/test_auth.py. Please implement fix."
        )


@pytest.mark.asyncio
async def test_simultaneous_takeover_race(
    takeover_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Mandatory Race Test: Two simultaneous takeovers -> exactly 1 succeeds, 1 conflicts."""
    app, _, proj_id, _, _, agent_id = takeover_app
    _, _, pem_priv, _ = rsa_keys
    token_alice = sign_token(pem_priv, "sub-alice")
    token_bob = sign_token(pem_priv, "sub-bob")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create task and assign to agent
        create_res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Race Condition Task"},
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        task_id = create_res.json()["id"]

        assign_res = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"assignee_type": "AGENT", "assignee_id": str(agent_id)},
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        current_version = assign_res.json()["version"]

        # Alice and Bob both attempt takeover simultaneously with expected_version = current_version
        alice_req = client.post(
            f"/api/v1/tasks/{task_id}/takeover",
            json={"reason": "Alice takeover", "expected_version": current_version},
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        bob_req = client.post(
            f"/api/v1/tasks/{task_id}/takeover",
            json={"reason": "Bob takeover", "expected_version": current_version},
            headers={"Authorization": f"Bearer {token_bob}"},
        )

        res_alice, res_bob = await asyncio.gather(alice_req, bob_req)

        status_codes = [res_alice.status_code, res_bob.status_code]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"Expected 1 success, got {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"Expected 1 conflict, got {status_codes}"
        )
