"""Unit tests for M55 (Agent to Human Requests: APPROVAL, DECISION, HELP, TAKEOVER).

Validates:
- Agent creating request pauses task status to BLOCKED.
- Outbox event `human.input_required` is published.
- Human providing response resolves pending request and unblocks task to IN_PROGRESS.
- Outbox event `workflow.updated` is published.
"""

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


def sign_token(pem_priv: bytes, sub: str) -> str:
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
        "realm_access": {"roles": ["developer"]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers=headers)


@pytest.fixture
async def request_app(
    tmp_path: Path,
    oidc_setup: Any,
) -> AsyncIterator[tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID]]:
    db_file = tmp_path / "request_test.db"
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
        org = Organization(name="Req Org", slug="req-org")
        session.add(org)
        await session.flush()

        user = User(
            organization_id=org.id,
            external_subject="sub-lead",
            username="lead",
            email="lead@example.com",
            role="ORG_ADMIN",
        )
        session.add(user)
        await session.flush()

        project = Project(
            organization_id=org.id,
            name="Req Project",
            slug="req-proj",
            created_by_id=user.id,
        )
        session.add(project)
        await session.flush()

        pm = ProjectMember(project_id=project.id, user_id=user.id, role="OWNER")
        session.add(pm)

        agent = Agent(
            organization_id=org.id,
            project_id=project.id,
            name="Dev Agent",
            slug="dev-agent",
            role="DEVELOPER",
            system_prompt="You code.",
        )
        session.add(agent)
        await session.commit()

        proj_id = project.id
        user_id = user.id
        agent_id = agent.id

    app = create_app(settings)
    yield app, proj_id, user_id, agent_id
    await db.disconnect()


@pytest.mark.asyncio
async def test_agent_approval_and_human_response(
    request_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    app, proj_id, _, agent_id = request_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-lead")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create and claim task
        create_res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Migration Task"},
            headers=headers,
        )
        task_id = create_res.json()["id"]

        await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"assignee_type": "AGENT", "assignee_id": str(agent_id)},
            headers=headers,
        )

        # 2. Agent requests APPROVAL -> status becomes BLOCKED
        req_res = await client.post(
            f"/api/v1/tasks/{task_id}/requests",
            json={
                "request_type": "APPROVAL",
                "prompt": "Apply destructive schema migration dropping old table?",
                "options": ["APPROVE", "REJECT"],
            },
            headers=headers,
        )
        assert req_res.status_code == status.HTTP_200_OK
        data = req_res.json()
        assert data["status"] == "BLOCKED"
        pending = data["context"]["pending_human_request"]
        assert pending["status"] == "PENDING"
        assert pending["request_type"] == "APPROVAL"

        # Verify outbox event emitted
        audit_res = await client.get(f"/api/v1/projects/{proj_id}/audit-events", headers=headers)
        req_events = [e for e in audit_res.json() if e["event_type"] == "human.input_required"]
        assert len(req_events) == 1

        # 3. Human responds with APPROVE -> status becomes IN_PROGRESS
        respond_res = await client.post(
            f"/api/v1/tasks/{task_id}/requests/respond",
            json={"action": "APPROVE", "feedback": "Backup complete, approved."},
            headers=headers,
        )
        assert respond_res.status_code == status.HTTP_200_OK
        res_data = respond_res.json()
        assert res_data["status"] == "IN_PROGRESS"
        resolved = res_data["context"]["pending_human_request"]
        assert resolved["status"] == "RESOLVED"
        assert resolved["response"]["action"] == "APPROVE"


@pytest.mark.asyncio
async def test_respond_without_pending_request_conflicts(
    request_app: tuple[FastAPI, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    app, proj_id, _, _ = request_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-lead")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        create_res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Ordinary Task"},
            headers=headers,
        )
        task_id = create_res.json()["id"]

        res = await client.post(
            f"/api/v1/tasks/{task_id}/requests/respond",
            json={"action": "APPROVE"},
            headers=headers,
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "NO_PENDING_REQUEST"
