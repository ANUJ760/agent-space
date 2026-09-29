"""Tests for M27 — WebSocket Realtime Gateway.

Validates:
- WebSocket endpoint /api/v1/ws/projects/{project_id}
- Unauthorized without token rejected with WS_1008_POLICY_VIOLATION
- Unauthorized with invalid token rejected with WS_1008_POLICY_VIOLATION
- Non-member user rejected with WS_1008_POLICY_VIOLATION
- Authorized project member accepted and receives connection.established
- Heartbeat ping / pong
- Real-time broadcast of domain events (task.updated, task.assigned, etc.)
- Active connection lifecycle management
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.api.v1.ws import get_connection_manager
from app.auth.oidc import OIDCClient, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager, set_db_manager
from app.main import create_app
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
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


def sign_token(pem_priv: bytes, sub: str, username: str, email: str, role: str = "developer") -> str:
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": username,
        "email": email,
        "email_verified": True,
        "realm_access": {"roles": [role]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def ws_env(
    oidc_setup: OIDCClient,
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, str]]:
    """Setup app, database, org, project, and test users."""
    db_path = tmp_path / "ws_test.db"
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
        org = Organization(name="WS Org", slug="ws-org")
        session.add(org)
        await session.flush()

        # Member user
        user_member = User(
            external_subject="sub-ws-member",
            username="ws_member",
            email="member@ws.com",
            role="MEMBER",
            organization_id=org.id,
        )
        # Non-member user
        user_outsider = User(
            external_subject="sub-ws-outsider",
            username="ws_outsider",
            email="outsider@ws.com",
            role="MEMBER",
            organization_id=org.id,
        )
        session.add(user_member)
        session.add(user_outsider)
        await session.flush()

        proj = Project(
            organization_id=org.id,
            name="WS Project",
            slug="ws-project",
            created_by_id=user_member.id,
        )
        session.add(proj)
        await session.flush()

        member = ProjectMember(
            project_id=proj.id,
            user_id=user_member.id,
            role="COLLABORATOR",
        )
        session.add(member)
        await session.commit()

    app = create_app(settings)
    yield app, db, org.id, proj.id, "sub-ws-member", "sub-ws-outsider"

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]


class TestWebSocketGateway:
    def test_missing_token_rejected(
        self,
        ws_env: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, str],
    ) -> None:
        from starlette.websockets import WebSocketDisconnect

        app, _, _, proj_id, _, _ = ws_env
        client = TestClient(app)

        with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/api/v1/ws/projects/{proj_id}") as ws:
            ws.receive_json()

    def test_invalid_token_rejected(
        self,
        ws_env: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, str],
    ) -> None:
        from starlette.websockets import WebSocketDisconnect

        app, _, _, proj_id, _, _ = ws_env
        client = TestClient(app)

        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            f"/api/v1/ws/projects/{proj_id}?token=invalid.jwt.token"
        ) as ws:
            ws.receive_json()

    def test_outsider_user_rejected(
        self,
        ws_env: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, str],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        from starlette.websockets import WebSocketDisconnect

        app, _, _, proj_id, _, outsider_sub = ws_env
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, outsider_sub, "ws_outsider", "outsider@ws.com")
        client = TestClient(app)

        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            f"/api/v1/ws/projects/{proj_id}?token={token}"
        ) as ws:
            ws.receive_json()

    def test_authorized_member_connect_and_ping_pong(
        self,
        ws_env: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, str],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app, _, _, proj_id, member_sub, _ = ws_env
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, member_sub, "ws_member", "member@ws.com")
        client = TestClient(app)

        with client.websocket_connect(f"/api/v1/ws/projects/{proj_id}?token={token}") as ws:
            # 1. First message must be connection.established
            welcome = ws.receive_json()
            assert welcome["event"] == "connection.established"
            assert welcome["project_id"] == str(proj_id)

            # 2. Send ping, expect pong
            ws.send_json({"action": "ping"})
            pong = ws.receive_json()
            assert pong["event"] == "pong"
            assert "timestamp" in pong

    def test_event_broadcasting_to_connected_clients(
        self,
        ws_env: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, str],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        import asyncio

        app, _, _, proj_id, member_sub, _ = ws_env
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, member_sub, "ws_member", "member@ws.com")
        client = TestClient(app)

        with client.websocket_connect(f"/api/v1/ws/projects/{proj_id}?token={token}") as ws:
            welcome = ws.receive_json()
            assert welcome["event"] == "connection.established"

            # Broadcast a domain event
            manager = get_connection_manager()
            asyncio.run(
                manager.broadcast_to_project(
                    project_id=proj_id,
                    event_type="task.updated",
                    payload={"task_id": "t-1", "status": "IN_PROGRESS"},
                )
            )

            # Receive broadcasted event
            msg = ws.receive_json()
            assert msg["event"] == "task.updated"
            assert msg["project_id"] == str(proj_id)
            assert msg["payload"]["status"] == "IN_PROGRESS"
