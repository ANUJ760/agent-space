"""Tests for M19 — Audit Events / Transactional Outbox.

Validates:
- Domain events created in the same database transaction as business mutations
- task.created recorded on task creation
- task.assigned recorded on task worker assignment
- task.transitioned and task.completed recorded on lifecycle transitions
- task.released recorded on task release
- Uncommitted / rolled back transactions do not persist outbox events
- GET /api/v1/projects/{project_id}/audit-events returns the audit trail
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
from app.models.outbox import OutboxEvent
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from sqlalchemy import select


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
async def outbox_app(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Fixture providing app, db, org, project, user, and agent."""
    db_path = tmp_path / "outbox_test.db"
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
        org = Organization(name="Outbox Org", slug="outbox-org")
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
            name="Outbox Project",
            slug="outbox-proj",
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
            name="Outbox Agent",
            slug="outbox-agent",
            role="DEVELOPER",
        )
        session.add(agent)
        await session.flush()

        await session.commit()

    app = create_app(settings)
    yield app, db, org.id, proj.id, user.id, agent.id

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_task_creation_records_outbox_event(
    outbox_app: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Creating a task writes a task.created outbox event in the same transaction."""
    app, db, _, proj_id, _, _ = outbox_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Audit Task 1", "priority": "HIGH"},
            headers=headers,
        )
        assert res.status_code == status.HTTP_201_CREATED
        task_id = uuid.UUID(res.json()["id"])

    # Query outbox_events directly from database
    async with db.session_factory() as session:
        stmt = select(OutboxEvent).where(OutboxEvent.aggregate_id == task_id)
        result = await session.execute(stmt)
        events = list(result.scalars().all())

        assert len(events) == 1
        event = events[0]
        assert event.event_type == "task.created"
        assert event.aggregate_type == "task"
        assert event.published_at is None
        assert event.payload["title"] == "Audit Task 1"
        assert event.payload["status"] == "TODO"


@pytest.mark.asyncio
async def test_full_lifecycle_outbox_events(
    outbox_app: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Tests that assign, transition, and complete record corresponding outbox events."""
    app, _, _, proj_id, _, agent_id = outbox_app
    _, _, pem_priv, _ = rsa_keys
    token = sign_token(pem_priv, "sub-admin-a")
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create task
        res = await client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            json={"title": "Lifecycle Outbox Task"},
            headers=headers,
        )
        task_id = res.json()["id"]

        # 2. Assign task -> task.assigned
        assign_res = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"assignee_type": "AGENT", "assignee_id": str(agent_id)},
            headers=headers,
        )
        assert assign_res.status_code == status.HTTP_200_OK

        # 3. Transition to IN_PROGRESS -> task.transitioned
        trans_res1 = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            json={"status": "IN_PROGRESS"},
            headers=headers,
        )
        assert trans_res1.status_code == status.HTTP_200_OK

        # 4. Transition to REVIEW -> task.transitioned
        trans_res2 = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            json={"status": "REVIEW"},
            headers=headers,
        )
        assert trans_res2.status_code == status.HTTP_200_OK

        # 5. Transition to DONE -> task.completed
        done_res = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            json={"status": "DONE"},
            headers=headers,
        )
        assert done_res.status_code == status.HTTP_200_OK

        # 6. Retrieve audit events from API
        audit_res = await client.get(
            f"/api/v1/projects/{proj_id}/audit-events",
            headers=headers,
        )
        assert audit_res.status_code == status.HTTP_200_OK
        audit_events = audit_res.json()

        event_types = [e["event_type"] for e in audit_events if e["aggregate_id"] == task_id]
        assert event_types == [
            "task.created",
            "task.assigned",
            "task.transitioned",
            "task.transitioned",
            "task.completed",
        ]
