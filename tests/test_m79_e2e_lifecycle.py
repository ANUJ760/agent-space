"""End-to-End Task Lifecycle Integration Test Suite (M79).

Validates the full enterprise lifecycle per Build Guide Section 88:
login
 ↓
create project
 ↓
create tasks
 ↓
dependencies
 ↓
assign agent
 ↓
execute
 ↓
artifact
 ↓
review
 ↓
complete
"""

import hashlib
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
from app.models.agent import Agent
from app.models.artifact import Artifact
from app.models.organization import Organization
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from agents.coding_agent import CodingAgent
from agents.protocol import AgentExecutionStatus, TaskContext
from packages.storage.artifact_store import LocalStorageArtifactStore


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


def sign_token(pem_priv: bytes, sub: str, email: str, role: str) -> str:
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": sub,
        "email": email,
        "email_verified": True,
        "realm_access": {"roles": [role.lower()]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def e2e_environment(
    oidc_setup: OIDCClient, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID, Path]]:
    """Set up database, organization, user, and agent for the E2E lifecycle."""
    db_path = tmp_path / "e2e_test.db"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

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
        org = Organization(name="Acme Enterprise", slug="acme-enterprise")
        session.add(org)
        await session.flush()

        lead_dev = User(
            external_subject="sub-lead-dev",
            username="lead_dev",
            email="lead@acme.com",
            role="ORG_ADMIN",
            organization_id=org.id,
        )
        session.add(lead_dev)
        await session.flush()

        coding_agent = Agent(
            organization_id=org.id,
            name="Autonomous Coding Agent",
            slug="auto-coding-agent",
            role="developer",
            model="gpt-4o",
            model_provider="openai",
            status="READY",
            capabilities=["PYTHON", "FASTAPI", "GIT"],
        )
        session.add(coding_agent)
        await session.commit()

        org_id = org.id
        user_id = lead_dev.id
        agent_id = coding_agent.id

    app = create_app(settings)
    app.state.db = db
    yield app, db, org_id, user_id, agent_id, artifacts_dir

    await db.disconnect()


@pytest.mark.asyncio
async def test_full_e2e_task_lifecycle(
    e2e_environment: tuple[FastAPI, DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID, Path],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Execute the complete end-to-end scenario:

    1. login
    2. create project
    3. create tasks (Task 1: Core Service, Task 2: Deployment)
    4. dependencies (Task 2 depends on Task 1)
    5. assign agent to Task 1
    6. execute Task 1 with CodingAgent
    7. artifact generated and persisted in CAS
    8. review Task 1 and approve
    9. complete Task 1 -> unblocks Task 2 -> complete Task 2 -> 100% project completion
    """
    app, db, org_id, user_id, agent_id, artifacts_dir = e2e_environment
    _, _, pem_priv, _ = rsa_keys

    # =========================================================================
    # Step 1: LOGIN (Authenticate session)
    # =========================================================================
    token = sign_token(pem_priv, sub="sub-lead-dev", email="lead@acme.com", role="ORG_ADMIN")

    with TestClient(app) as client:
        # Verify authenticated identity
        auth_me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert auth_me_resp.status_code == status.HTTP_200_OK
        user_data = auth_me_resp.json()
        assert user_data["email"] == "lead@acme.com"
        assert user_data["organization"]["id"] == str(org_id)

        # =====================================================================
        # Step 2: CREATE PROJECT
        # =====================================================================
        create_proj_resp = client.post(
            "/api/v1/projects",
            json={
                "name": "Cloud Native URL Shortener",
                "slug": "url-shortener",
                "description": "Production URL shortener service with analytics",
                "default_branch": "main",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_proj_resp.status_code == status.HTTP_201_CREATED
        project = create_proj_resp.json()
        project_id = project["id"]
        assert project["status"] == "ACTIVE"
        assert project["slug"] == "url-shortener"

        # =====================================================================
        # Step 3: CREATE TASKS
        # =====================================================================
        # Task 1: Core Feature Implementation
        t1_resp = client.post(
            f"/api/v1/projects/{project_id}/tasks",
            json={
                "title": "Build URL Shortener API",
                "description": "Implement FastAPI routes for hashing URLs and redirection",
                "priority": "HIGH",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert t1_resp.status_code == status.HTTP_201_CREATED
        task_1 = t1_resp.json()
        task_1_id = task_1["id"]
        assert task_1["status"] == "TODO"
        assert task_1["version"] == 1

        # Task 2: Deployment & Verification (dependent task)
        t2_resp = client.post(
            f"/api/v1/projects/{project_id}/tasks",
            json={
                "title": "Deploy Service & Verify Analytics",
                "description": "Deploy to staging container and assert 302 redirect analytics",
                "priority": "CRITICAL",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert t2_resp.status_code == status.HTTP_201_CREATED
        task_2 = t2_resp.json()
        task_2_id = task_2["id"]
        assert task_2["status"] == "TODO"

        # =====================================================================
        # Step 4: ESTABLISH DEPENDENCY DAG & ENFORCE EXECUTION GUARDS
        # =====================================================================
        # Task 2 depends on Task 1
        dep_resp = client.post(
            f"/api/v1/tasks/{task_2_id}/dependencies",
            json={"depends_on_task_id": task_1_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert dep_resp.status_code == status.HTTP_201_CREATED
        assert dep_resp.json()["depends_on_task_id"] == task_1_id

        # Verify DAG guard: Task 2 CANNOT execute before Task 1 is DONE
        blocked_start_resp = client.patch(
            f"/api/v1/tasks/{task_2_id}",
            json={"status": "IN_PROGRESS"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert blocked_start_resp.status_code == status.HTTP_409_CONFLICT
        assert blocked_start_resp.json()["code"] == "TASK_DEPENDENCIES_UNRESOLVED"

        # =====================================================================
        # Step 5: ASSIGN AGENT
        # =====================================================================
        assign_resp = client.patch(
            f"/api/v1/tasks/{task_1_id}",
            json={
                "assigned_agent_id": str(agent_id),
                "status": "CLAIMED",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert assign_resp.status_code == status.HTTP_200_OK
        assigned_task = assign_resp.json()
        assert assigned_task["assigned_agent_id"] == str(agent_id)
        assert assigned_task["status"] == "CLAIMED"
        assert assigned_task["version"] == 2

        # =====================================================================
        # Step 6: EXECUTE TASK VIA AGENT
        # =====================================================================
        # Transition task to IN_PROGRESS
        start_exec_resp = client.patch(
            f"/api/v1/tasks/{task_1_id}",
            json={"status": "IN_PROGRESS"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert start_exec_resp.status_code == status.HTTP_200_OK
        assert start_exec_resp.json()["status"] == "IN_PROGRESS"

        # Execute coding agent logic
        agent = CodingAgent(name="Autonomous Coding Agent")
        context = TaskContext(
            task_id=task_1_id,
            project_id=project_id,
            title=task_1["title"],
            description=task_1["description"],
            metadata={"base_branch": "main", "feature_branch": f"feature/task-{task_1_id[:8]}"},
        )
        result = await agent.execute(context)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert len(result.changed_files) > 0

        # =====================================================================
        # Step 7: PERSIST ARTIFACT IN CAS
        # =====================================================================
        artifact_store = LocalStorageArtifactStore(base_dir=artifacts_dir)
        source_code = b"""# URL Shortener implementation
from fastapi import FastAPI, HTTPException
import hashlib

app = FastAPI(title="URL Shortener")
urls: dict[str, str] = {}

@app.post("/shorten")
def shorten(url: str) -> dict:
    code = hashlib.md5(url.encode()).hexdigest()[:6]
    urls[code] = url
    return {"code": code, "short_url": f"https://sho.rt/{code}"}
"""
        code_sha256 = hashlib.sha256(source_code).hexdigest()
        storage_key = f"{project_id}/artifacts/{task_1_id}/main.py"
        stored_sha = await artifact_store.put(
            storage_key, source_code, content_type="text/x-python"
        )
        assert stored_sha == code_sha256
        assert await artifact_store.exists(storage_key)

        # Store artifact metadata record in database
        async with db.session_factory() as session:
            art_record = Artifact(
                organization_id=org_id,
                project_id=uuid.UUID(project_id),
                task_id=uuid.UUID(task_1_id),
                agent_id=agent_id,
                created_by_id=user_id,
                storage_key=storage_key,
                filename="main.py",
                content_type="text/x-python",
                size_bytes=len(source_code),
                sha256_hash=code_sha256,
                artifact_type="CODE",
                metadata_json={"loc": 14, "language": "python"},
            )
            session.add(art_record)
            await session.commit()
            artifact_id = art_record.id

        # Verify presigned URL retrieval for artifact
        presigned_url = await artifact_store.presign(storage_key, expires_in_seconds=3600)
        assert "expires=" in presigned_url
        assert "signature=" in presigned_url

        # =====================================================================
        # Step 8: REVIEW TASK
        # =====================================================================
        # Task transitions from IN_PROGRESS to REVIEW
        review_transition = client.patch(
            f"/api/v1/tasks/{task_1_id}",
            json={"status": "REVIEW"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert review_transition.status_code == status.HTTP_200_OK
        assert review_transition.json()["status"] == "REVIEW"

        # Reviewer inspects artifact and approves
        async with db.session_factory() as session:
            fetched_art = await session.get(Artifact, artifact_id)
            assert fetched_art is not None
            assert fetched_art.sha256_hash == code_sha256
            assert fetched_art.artifact_type == "CODE"

        # =====================================================================
        # Step 9: COMPLETE TASK & UNBLOCK DOWNSTREAM
        # =====================================================================
        # Approve and mark Task 1 DONE
        complete_t1_resp = client.patch(
            f"/api/v1/tasks/{task_1_id}",
            json={"status": "DONE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert complete_t1_resp.status_code == status.HTTP_200_OK
        assert complete_t1_resp.json()["status"] == "DONE"

        # Verify downstream Task 2 is now unblocked and can execute!
        start_t2_resp = client.patch(
            f"/api/v1/tasks/{task_2_id}",
            json={"status": "IN_PROGRESS"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert start_t2_resp.status_code == status.HTTP_200_OK
        assert start_t2_resp.json()["status"] == "IN_PROGRESS"

        # Complete Task 2
        complete_t2_resp = client.patch(
            f"/api/v1/tasks/{task_2_id}",
            json={"status": "DONE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert complete_t2_resp.status_code == status.HTTP_200_OK
        assert complete_t2_resp.json()["status"] == "DONE"

        # Verify project task metrics: both tasks are DONE
        list_tasks_resp = client.get(
            f"/api/v1/projects/{project_id}/tasks",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_tasks_resp.status_code == status.HTTP_200_OK
        all_tasks = list_tasks_resp.json()
        assert len(all_tasks) == 2
        assert all(t["status"] == "DONE" for t in all_tasks)
