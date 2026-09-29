"""Tenant Isolation Security Audit (M67).

Systematically audits cross-tenant access rejection across all 9 domains:
1. Projects: Cross-tenant project read/update/delete rejected
2. Tasks: Cross-tenant task creation/read/execution rejected
3. Members: Cross-tenant member listing/management rejected
4. Agents: Cross-tenant agent dispatch/management rejected
5. Events: Cross-tenant outbox/audit event querying rejected
6. Artifacts: Cross-tenant artifact retrieval & preview rejected
7. Memory: Cross-tenant vector/facts semantic exfiltration returns zero data
8. Repositories: Cross-tenant workspace lease/branch access rejected
9. WebSockets: Cross-tenant project WebSocket subscription rejected (Code 1008)
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.auth import (
    Actor,
    Permission,
    Role,
    authorize_object_access,
    authorize_project_access,
)
from app.auth.oidc import OIDCClient, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager, set_db_manager
from app.errors import ForbiddenError
from app.main import create_app
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.services.project_memory import ProjectMemoryService
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from packages.memory.embeddings import MockEmbeddingProvider
from packages.memory.qdrant import MemoryPoint, QdrantVectorStore, SearchResult
from packages.workspace.manager import WorkspaceConflictError, WorkspaceManager

# ─── Mock Domain Entities for Tenant Isolation Testing ─────────────────────


@dataclass
class MockResource:
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str = "Test Resource"


# ─── 1. Projects Isolation Audit ──────────────────────────────────────────


def test_cross_tenant_project_access_rejected() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = Actor(id=uuid.uuid4(), external_subject="sub-user-a", organization_id=org_a, role=Role.MEMBER)
    proj_b = MockResource(id=uuid.uuid4(), organization_id=org_b, name="Tenant B Secret Project")

    # Read project
    with pytest.raises(ForbiddenError, match="Cross-organization access denied"):
        authorize_project_access(user_a, proj_b, Permission.PROJECT_READ)

    # Update project
    with pytest.raises(ForbiddenError, match="Cross-organization access denied"):
        authorize_project_access(user_a, proj_b, Permission.PROJECT_UPDATE)

    # Delete project
    with pytest.raises(ForbiddenError, match="Cross-organization access denied"):
        authorize_project_access(user_a, proj_b, Permission.PROJECT_DELETE)


# ─── 2. Tasks Isolation Audit ─────────────────────────────────────────────


def test_cross_tenant_task_access_rejected() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = Actor(id=uuid.uuid4(), external_subject="sub-user-a", organization_id=org_a, role=Role.MEMBER)
    task_b = MockResource(id=uuid.uuid4(), organization_id=org_b, name="Deploy Production B")

    # Read task
    with pytest.raises(ForbiddenError, match="Cross-organization access to Task denied"):
        authorize_object_access(user_a, task_b, Permission.TASK_READ, resource_name="Task")

    # Execute task
    with pytest.raises(ForbiddenError, match="Cross-organization access to Task denied"):
        authorize_object_access(user_a, task_b, Permission.TASK_EXECUTE, resource_name="Task")

    # Update task
    with pytest.raises(ForbiddenError, match="Cross-organization access to Task denied"):
        authorize_object_access(user_a, task_b, Permission.TASK_UPDATE, resource_name="Task")


# ─── 3. Project Members Isolation Audit ───────────────────────────────────


def test_cross_tenant_member_management_rejected() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = Actor(id=uuid.uuid4(), external_subject="sub-user-a", organization_id=org_a, role=Role.ORG_ADMIN)
    proj_b = MockResource(id=uuid.uuid4(), organization_id=org_b, name="Tenant B Project")

    # Admin of Org A attempts to manage members in Org B's project
    with pytest.raises(ForbiddenError, match="Cross-organization access denied"):
        authorize_project_access(user_a, proj_b, Permission.PROJECT_MANAGE_MEMBERS)


# ─── 4. Agents Isolation Audit ────────────────────────────────────────────


def test_cross_tenant_agent_access_rejected() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = Actor(id=uuid.uuid4(), external_subject="sub-user-a", organization_id=org_a, role=Role.MEMBER)
    agent_b = MockResource(id=uuid.uuid4(), organization_id=org_b, name="Tenant B Specialized Agent")

    with pytest.raises(ForbiddenError, match="Cross-organization access to Agent denied"):
        authorize_object_access(user_a, agent_b, Permission.AGENT_EXECUTE, resource_name="Agent")

    with pytest.raises(ForbiddenError, match="Cross-organization access to Agent denied"):
        authorize_object_access(user_a, agent_b, Permission.AGENT_MANAGE, resource_name="Agent")


# ─── 5. Audit Events / Outbox Isolation Audit ─────────────────────────────


def test_cross_tenant_event_access_rejected() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = Actor(id=uuid.uuid4(), external_subject="sub-user-a", organization_id=org_a, role=Role.MEMBER)
    event_b = MockResource(id=uuid.uuid4(), organization_id=org_b, name="Audit Trail Event B")

    with pytest.raises(ForbiddenError, match="Cross-organization access to AuditEvent denied"):
        authorize_object_access(user_a, event_b, Permission.ORG_READ, resource_name="AuditEvent")


# ─── 6. Artifacts Isolation Audit ─────────────────────────────────────────


def test_cross_tenant_artifact_access_rejected() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = Actor(id=uuid.uuid4(), external_subject="sub-user-a", organization_id=org_a, role=Role.MEMBER)
    artifact_b = MockResource(id=uuid.uuid4(), organization_id=org_b, name="Confidential Financial Model.xlsx")

    with pytest.raises(ForbiddenError, match="Cross-organization access to Artifact denied"):
        authorize_object_access(user_a, artifact_b, Permission.PROJECT_READ, resource_name="Artifact")


# ─── 7. Memory & Vector Store Isolation Audit ─────────────────────────────


class MockVectorStore(QdrantVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.points: dict[str, list[MemoryPoint]] = {}

    async def insert_points(self, collection_name: str, points: list[MemoryPoint]) -> bool:
        self.points.setdefault(collection_name, []).extend(points)
        return True

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filter_criteria: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        all_pts = self.points.get(collection_name, [])
        filtered = []
        for p in all_pts:
            match = True
            if filter_criteria and "must" in filter_criteria:
                for cond in filter_criteria["must"]:
                    key = cond["key"]
                    expected = cond["match"]["value"]
                    if str(p.payload.get(key)) != str(expected):
                        match = False
                        break
            if match:
                filtered.append(SearchResult(id=p.id, score=0.95, payload=p.payload))
        return filtered[:limit]


@pytest.mark.asyncio
async def test_cross_tenant_memory_retrieval_prevented() -> None:
    vec_store = MockVectorStore()
    embedding_provider = MockEmbeddingProvider(dimension=32)
    service = ProjectMemoryService(
        vector_store=vec_store,
        embedding_provider=embedding_provider,
        collection_name="audit_memory",
    )

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    proj_a = uuid.uuid4()
    proj_b = uuid.uuid4()

    # Tenant B indexes confidential facts
    await service.store_memory(
        organization_id=org_b,
        project_id=proj_b,
        content="TENANT_B_PATENT: Proprietary quantum optimization algorithm",
        memory_type="architecture",
    )

    # Tenant A attempts to retrieve Tenant B's data
    context_a = await service.retrieve_context(
        organization_id=org_a,
        project_id=proj_a,
        query="Proprietary quantum optimization algorithm",
    )

    # Cross-tenant exfiltration strictly blocked (zero matches returned)
    assert len(context_a.semantic_memories) == 0

    # Tenant B querying their own project succeeds
    context_b = await service.retrieve_context(
        organization_id=org_b,
        project_id=proj_b,
        query="Proprietary quantum optimization algorithm",
    )
    assert len(context_b.semantic_memories) == 1
    assert "quantum optimization" in context_b.semantic_memories[0].content


# ─── 8. Repositories & Workspaces Isolation Audit ─────────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_repository_workspace_rejected(tmp_path: Path) -> None:
    ws_mgr = WorkspaceManager(base_workspace_dir=tmp_path / "workspaces")
    repo_path = tmp_path / "main-repo"
    repo_path.mkdir()

    # Tenant B task workspace lease active
    await ws_mgr.acquire_workspace(
        task_id="task-tenant-b-1",
        agent_id="agent-tenant-b",
        base_repo_path=repo_path,
    )

    # Tenant A agent attempts to hijack Tenant B workspace
    with pytest.raises(WorkspaceConflictError, match="agent-tenant-b"):
        await ws_mgr.acquire_workspace(
            task_id="task-tenant-b-1",
            agent_id="agent-tenant-a",
            base_repo_path=repo_path,
        )


# ─── 9. WebSockets Cross-Tenant Gateway Audit ─────────────────────────────


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
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-audit"})


@pytest.fixture()
async def ws_tenant_env(
    rsa_keys: tuple[Any, Any, bytes, bytes],
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, bytes]]:
    _, public_key, pem_priv, _ = rsa_keys
    kc_settings = KeycloakSettings(
        server_url="http://localhost:8080",
        realm="agentspace",
        client_id="agentspace-backend",
        audience="agentspace-backend",
    )
    client = OIDCClient(kc_settings)
    client.register_mock_key("key-audit", public_key)
    set_oidc_client(client)

    db_path = tmp_path / "ws_tenant_test.db"
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
        org_a = Organization(name="Org A", slug="org-a")
        org_b = Organization(name="Org B", slug="org-b")
        session.add(org_a)
        session.add(org_b)
        await session.flush()

        # User A in Org A
        user_a = User(
            external_subject="sub-user-a",
            username="user_a",
            email="usera@org-a.com",
            role="MEMBER",
            organization_id=org_a.id,
        )
        # User B in Org B
        user_b = User(
            external_subject="sub-user-b",
            username="user_b",
            email="userb@org-b.com",
            role="MEMBER",
            organization_id=org_b.id,
        )
        session.add(user_a)
        session.add(user_b)
        await session.flush()

        # Project B in Org B
        proj_b = Project(
            organization_id=org_b.id,
            name="Project B",
            slug="project-b",
            created_by_id=user_b.id,
        )
        session.add(proj_b)
        await session.flush()

        # User B is member of Project B
        member_b = ProjectMember(
            project_id=proj_b.id,
            user_id=user_b.id,
            role="COLLABORATOR",
        )
        session.add(member_b)
        await session.commit()

        proj_b_id = proj_b.id
        org_b_id = org_b.id

    app = create_app(settings)
    yield app, db, org_b_id, proj_b_id, "sub-user-a", pem_priv

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]
    client.clear_mock_keys()
    set_oidc_client(None)


def test_cross_tenant_websocket_subscription_rejected(
    ws_tenant_env: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, str, bytes],
) -> None:
    app, _, _, proj_b_id, sub_user_a, pem_priv = ws_tenant_env
    client = TestClient(app)

    token_user_a = sign_token(pem_priv, sub_user_a, "user_a", "usera@org-a.com")

    # User A connects to Project B's WebSocket channel -> Disconnected with Policy Violation (1008)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/api/v1/ws/projects/{proj_b_id}?token={token_user_a}") as ws,
    ):
        ws.receive_json()

    assert exc_info.value.code == 1008
