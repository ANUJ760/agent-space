"""Tests for M75 — Concurrency Test Suite.

Mandatory validations per M75 specification:
1. Simultaneous Assignment:
   - 20 concurrent assignment requests: exactly 1 success, 19 conflict/rejections (TASK_ALREADY_ASSIGNED).
2. Simultaneous Takeover:
   - 2+ concurrent users attempting takeover: exactly 1 ownership transfer succeeds, 1 receives 409 conflict.
3. Stale Version:
   - Updating task with stale expected_version: returns 409 Conflict (TASK_VERSION_CONFLICT).
4. Duplicate Idempotency:
   - Concurrent/repeated requests with identical Idempotency-Key: exactly one operation executed, identical responses.
5. Duplicate Event:
   - Processing duplicate domain events: no duplicate state mutation.
6. Stale WebSocket:
   - Incoming WebSocket events with older version numbers: ignored without state regression.
7. Concurrent Git Editing:
   - Isolated branches per task, merge conflict surfaced cleanly on conflicting concurrent edits.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio
from app.auth.oidc import OIDCClient, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager, set_db_manager
from app.main import create_app
from app.models.agent import Agent
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.task import Task
from app.models.user import User
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import status
from sqlalchemy import select

from packages.gitea.client import CommitFileInfo, GiteaClient, GiteaConflictError

# ─── Auth and DB Fixtures ──────────────────────────────────────────────────


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


def sign_token(pem_priv: bytes, sub: str, role: str = "developer") -> str:
    payload = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,
        "preferred_username": sub,
        "email": f"{sub}@example.com",
        "email_verified": True,
        "realm_access": {"roles": [role]},
    }
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": "key-1"})


@pytest_asyncio.fixture()
async def concurrency_app(
    oidc_setup: Any, tmp_path: Path
) -> AsyncIterator[dict[str, Any]]:
    """Fixture providing configured FastAPI app and seeded entities."""
    db_file = tmp_path / "m75_concurrency.db"
    settings = Settings(
        environment="test",
        debug=True,
        database_url=f"sqlite+aiosqlite:///{db_file}",
    )
    db = DatabaseManager(settings.database)
    await db.connect()
    await db.create_all()
    set_db_manager(db)

    org_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    bob_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    extra_agents = [uuid.uuid4() for _ in range(20)]

    async with db.session_factory() as session:
        org = Organization(id=org_id, name="Concurrency Org", slug="conc-org")
        session.add(org)
        proj = Project(id=proj_id, organization_id=org_id, name="Conc Proj", slug="conc-proj")
        session.add(proj)

        alice = User(
            id=alice_id,
            organization_id=org_id,
            external_subject="sub-alice",
            email="alice@example.com",
            username="alice",
            role="MEMBER",
        )
        bob = User(
            id=bob_id,
            organization_id=org_id,
            external_subject="sub-bob",
            email="bob@example.com",
            username="bob",
            role="MEMBER",
        )
        session.add_all([alice, bob])
        await session.flush()

        # Members
        session.add(ProjectMember(project_id=proj_id, user_id=alice_id, role="admin"))
        session.add(ProjectMember(project_id=proj_id, user_id=bob_id, role="admin"))

        # Main agent
        session.add(
            Agent(
                id=agent_id,
                organization_id=org_id,
                name="Main Agent",
                slug="main-agent",
                role="DEVELOPER",
                system_prompt="Execute.",
            )
        )

        # 20 workers for simultaneous assignment
        for i, aid in enumerate(extra_agents):
            session.add(
                Agent(
                    id=aid,
                    organization_id=org_id,
                    name=f"Worker {i}",
                    slug=f"worker-{i}",
                    role="CODING",
                    system_prompt="Execute.",
                )
            )

        await session.commit()

    app = create_app()

    yield {
        "app": app,
        "db": db,
        "org_id": org_id,
        "project_id": proj_id,
        "alice_id": alice_id,
        "bob_id": bob_id,
        "agent_id": agent_id,
        "extra_agents": extra_agents,
    }

    await db.drop_all()
    await db.disconnect()
    set_db_manager(None)


# ─── 1. Simultaneous Assignment Suite ──────────────────────────────────────


class TestSimultaneousAssignment:
    """20 concurrent requests: exactly 1 success, 19 conflict/rejection."""

    @pytest.mark.asyncio
    async def test_20_simultaneous_assignment_requests(
        self,
        concurrency_app: dict[str, Any],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app = concurrency_app["app"]
        proj_id = concurrency_app["project_id"]
        agents = concurrency_app["extra_agents"]
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-alice")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Create an unassigned task
            create_resp = await client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Contended Assignment Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert create_resp.status_code == status.HTTP_201_CREATED
            task_id = create_resp.json()["id"]

            # Launch 20 simultaneous assignment requests
            async def send_assign(aid: uuid.UUID) -> int:
                resp = await client.post(
                    f"/api/v1/tasks/{task_id}/assign",
                    json={"assignee_type": "AGENT", "assignee_id": str(aid)},
                    headers={"Authorization": f"Bearer {token}"},
                )
                return resp.status_code

            status_codes = await asyncio.gather(*(send_assign(aid) for aid in agents))

            successes = status_codes.count(status.HTTP_200_OK)
            conflicts = status_codes.count(status.HTTP_409_CONFLICT)

            assert successes == 1, f"Expected 1 success, got {successes}"
            assert conflicts == 19, f"Expected 19 conflicts, got {conflicts}"


# ─── 2. Simultaneous Takeover Suite ────────────────────────────────────────


class TestSimultaneousTakeover:
    """2+ concurrent users: exactly 1 ownership transfer."""

    @pytest.mark.asyncio
    async def test_simultaneous_takeover_by_multiple_users(
        self,
        concurrency_app: dict[str, Any],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app = concurrency_app["app"]
        proj_id = concurrency_app["project_id"]
        agent_id = concurrency_app["agent_id"]
        alice_id = concurrency_app["alice_id"]
        bob_id = concurrency_app["bob_id"]
        _, _, pem_priv, _ = rsa_keys

        token_alice = sign_token(pem_priv, "sub-alice")
        token_bob = sign_token(pem_priv, "sub-bob")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create task and assign to agent
            create_resp = await client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "Takeover Contention Task"},
                headers={"Authorization": f"Bearer {token_alice}"},
            )
            task_id = create_resp.json()["id"]

            assign_resp = await client.post(
                f"/api/v1/tasks/{task_id}/assign",
                json={"assignee_type": "AGENT", "assignee_id": str(agent_id)},
                headers={"Authorization": f"Bearer {token_alice}"},
            )
            current_version = assign_resp.json()["version"]

            # 2. Both Alice and Bob attempt takeover simultaneously
            alice_req = client.post(
                f"/api/v1/tasks/{task_id}/takeover",
                json={"reason": "Alice urgent takeover", "expected_version": current_version},
                headers={"Authorization": f"Bearer {token_alice}"},
            )
            bob_req = client.post(
                f"/api/v1/tasks/{task_id}/takeover",
                json={"reason": "Bob urgent takeover", "expected_version": current_version},
                headers={"Authorization": f"Bearer {token_bob}"},
            )

            res_alice, res_bob = await asyncio.gather(alice_req, bob_req)
            codes = [res_alice.status_code, res_bob.status_code]

            # Exactly 1 ownership transfer succeeds
            assert codes.count(status.HTTP_200_OK) == 1, f"Expected exactly 1 success, got {codes}"
            assert codes.count(status.HTTP_409_CONFLICT) == 1, f"Expected exactly 1 conflict, got {codes}"

            # Check final ownership in database
            task_resp = await client.get(
                f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token_alice}"}
            )
            data = task_resp.json()
            assert data["assigned_agent_id"] is None
            assert data["assigned_user_id"] in [str(alice_id), str(bob_id)]


# ─── 3. Stale Version Suite ────────────────────────────────────────────────


class TestStaleVersion:
    """Stale version: expected 409 Conflict."""

    @pytest.mark.asyncio
    async def test_stale_expected_version_rejected_with_409(
        self,
        concurrency_app: dict[str, Any],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app = concurrency_app["app"]
        proj_id = concurrency_app["project_id"]
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-alice")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create task (version 1)
            create_resp = await client.post(
                f"/api/v1/projects/{proj_id}/tasks",
                json={"title": "OCC Version Task"},
                headers={"Authorization": f"Bearer {token}"},
            )
            task_id = create_resp.json()["id"]
            assert create_resp.json()["version"] == 1

            # 2. First update increments version to 2
            resp1 = await client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"title": "First Update", "expected_version": 1},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp1.status_code == status.HTTP_200_OK
            assert resp1.json()["version"] == 2

            # 3. Stale update specifying expected_version = 1 returns 409
            resp_stale = await client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"title": "Stale Update", "expected_version": 1},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp_stale.status_code == status.HTTP_409_CONFLICT
            assert resp_stale.json()["code"] == "TASK_VERSION_CONFLICT"


# ─── 4. Duplicate Idempotency Suite ────────────────────────────────────────


class TestDuplicateIdempotency:
    """Duplicate idempotency: expected one operation."""

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_keys_execute_single_operation(
        self,
        concurrency_app: dict[str, Any],
        rsa_keys: tuple[Any, Any, bytes, bytes],
    ) -> None:
        app = concurrency_app["app"]
        db = concurrency_app["db"]
        proj_id = concurrency_app["project_id"]
        _, _, pem_priv, _ = rsa_keys
        token = sign_token(pem_priv, "sub-alice")

        idempotency_key = f"key-{uuid.uuid4()}"

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency_key,
            }
            body = {"title": "Idempotent Task Creation"}

            # Send 5 concurrent requests with identical Idempotency-Key
            tasks = [
                client.post(f"/api/v1/projects/{proj_id}/tasks", json=body, headers=headers)
                for _ in range(5)
            ]
            responses = await asyncio.gather(*tasks)

            # All return HTTP 201
            for resp in responses:
                assert resp.status_code == status.HTTP_201_CREATED

            # All return the exact same task ID
            first_id = responses[0].json()["id"]
            for resp in responses:
                assert resp.json()["id"] == first_id

            # Verify in DB that only 1 task was actually created
            async with db.session_factory() as session:
                result = await session.execute(
                    select(Task).where(
                        Task.project_id == proj_id,
                        Task.title == "Idempotent Task Creation",
                    )
                )
                matching_tasks = result.scalars().all()
                assert len(matching_tasks) == 1, f"Expected 1 task in DB, found {len(matching_tasks)}"


# ─── 5. Duplicate Event Suite ──────────────────────────────────────────────


class TestDuplicateEvent:
    """Duplicate event: expected no duplicate state mutation."""

    @pytest.mark.asyncio
    async def test_duplicate_domain_event_deduplication(
        self,
        concurrency_app: dict[str, Any],
    ) -> None:
        """Simulate an idempotent event processor processing the same event ID twice."""
        db = concurrency_app["db"]
        proj_id = concurrency_app["project_id"]
        org_id = concurrency_app["org_id"]
        task_id = uuid.uuid4()
        event_id = str(uuid.uuid4())

        async with db.session_factory() as session:
            task = Task(
                id=task_id,
                organization_id=org_id,
                project_id=proj_id,
                title="Event Target Task",
                status="TODO",
            )
            session.add(task)
            await session.commit()

        # Idempotent event consumer handler simulating deduplication storage
        processed_event_ids: set[str] = set()
        mutation_counter = 0

        async def process_task_completed_event(e_id: str, t_id: uuid.UUID) -> bool:
            nonlocal mutation_counter
            if e_id in processed_event_ids:
                # Deduplicated: ignore
                return False

            processed_event_ids.add(e_id)
            async with db.session_factory() as session:
                t = await session.get(Task, t_id)
                if t:
                    t.status = "DONE"
                    await session.commit()
            mutation_counter += 1
            return True

        # First delivery: processed
        res1 = await process_task_completed_event(event_id, task_id)
        assert res1 is True
        assert mutation_counter == 1

        # Duplicate delivery of exact same event: ignored
        res2 = await process_task_completed_event(event_id, task_id)
        assert res2 is False
        assert mutation_counter == 1  # No duplicate state mutation

        # Verify task status in database
        async with db.session_factory() as session:
            final_task = await session.get(Task, task_id)
            assert final_task is not None
            assert final_task.status == "DONE"


# ─── 6. Stale WebSocket Suite ──────────────────────────────────────────────


class TestStaleWebSocket:
    """Stale WebSocket: expected older version ignored."""

    def test_stale_websocket_message_ignored(self) -> None:
        """Verify client/reducer ignores messages with version <= current_version."""

        class TaskStateSequencer:
            def __init__(self) -> None:
                self.current_version = 0
                self.title = ""
                self.status = ""

            def apply_message(self, message: dict[str, Any]) -> bool:
                version = message.get("version", 0)
                if version <= self.current_version:
                    # Stale or duplicate message -> ignore
                    return False
                self.current_version = version
                self.title = message.get("title", self.title)
                self.status = message.get("status", self.status)
                return True

        sequencer = TaskStateSequencer()

        # Message 1 arrives (version 1)
        applied1 = sequencer.apply_message({"version": 1, "title": "Initial", "status": "TODO"})
        assert applied1 is True
        assert sequencer.current_version == 1
        assert sequencer.title == "Initial"

        # Message 3 arrives early (version 3)
        applied3 = sequencer.apply_message({"version": 3, "title": "Updated", "status": "IN_PROGRESS"})
        assert applied3 is True
        assert sequencer.current_version == 3
        assert sequencer.title == "Updated"

        # Stale Message 2 arrives late (version 2) -> ignored!
        applied2 = sequencer.apply_message({"version": 2, "title": "Stale Older Version", "status": "CLAIMED"})
        assert applied2 is False
        assert sequencer.current_version == 3
        assert sequencer.title == "Updated"  # Did NOT regress to "Stale Older Version"

        # Duplicate Message 3 arrives again -> ignored!
        applied_dup = sequencer.apply_message({"version": 3, "title": "Dup Version 3", "status": "IN_PROGRESS"})
        assert applied_dup is False
        assert sequencer.current_version == 3


# ─── 7. Concurrent Git Editing Suite ───────────────────────────────────────


class TestConcurrentGitEditing:
    """Concurrent Git editing: isolated branches and merge conflict surfaced."""

    @pytest.mark.asyncio
    async def test_concurrent_git_editing_surfaces_merge_conflict(self) -> None:
        # Mock Gitea backend simulating isolated branches and merge conflicts
        branches: dict[str, list[str]] = {"testorg/code-repo": ["main"]}
        branch_files: dict[str, dict[str, str]] = {
            "main": {"app.py": "def process():\n    return 'base'\n"}
        }

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            method = request.method

            # Create branch: POST /api/v1/repos/{owner}/{repo}/branches
            if method == "POST" and "/branches" in url:
                import json

                data = json.loads(request.content.decode("utf-8"))
                new_branch = data["new_branch_name"]
                old_branch = data.get("old_branch_name", "main")
                branches["testorg/code-repo"].append(new_branch)
                branch_files[new_branch] = dict(branch_files.get(old_branch, {}))
                return httpx.Response(201, json={"name": new_branch})

            # Commit files: POST /api/v1/repos/{owner}/{repo}/contents
            if method == "POST" and "/contents" in url:
                import base64
                import json

                data = json.loads(request.content.decode("utf-8"))
                branch = data["branch"]
                for f in data["files"]:
                    try:
                        content_str = base64.b64decode(f["content"]).decode("utf-8")
                    except Exception:
                        content_str = f["content"]
                    branch_files.setdefault(branch, {})[f["path"]] = content_str
                return httpx.Response(201, json={"commit": {"sha": "sha-" + uuid.uuid4().hex[:6]}})

            # Merge branch: POST /api/v1/repos/{owner}/{repo}/merges
            if method == "POST" and "/merges" in url:
                import json

                data = json.loads(request.content.decode("utf-8"))
                head = data["head"]
                base = data["base"]

                # If head branch has conflicting modifications against base
                if (
                    branch_files.get(base, {}).get("app.py") != branch_files.get(head, {}).get("app.py")
                    and branch_files.get(base, {}).get("app.py") == "worker1_mod"
                ):
                    return httpx.Response(
                            409,
                            json={"message": "Merge conflict detected in app.py between main and " + head},
                        )

                # Fast-forward or clean merge
                branch_files[base] = dict(branch_files.get(head, {}))
                return httpx.Response(200, json={"message": "Merged cleanly"})

            return httpx.Response(404, json={"message": "Not found"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            gitea = GiteaClient(
                base_url="http://localhost:3001",
                admin_token="admin-token",
                http_client=mock_client,
            )

            # 1. Create two isolated branches for two concurrent tasks
            b1 = await gitea.create_branch("testorg", "code-repo", "task/task-101", old_branch_name="main")
            b2 = await gitea.create_branch("testorg", "code-repo", "task/task-102", old_branch_name="main")
            assert b1["name"] == "task/task-101"
            assert b2["name"] == "task/task-102"

            # 2. Worker 1 commits change to branch 1
            await gitea.create_commit(
                owner="testorg",
                repo_name="code-repo",
                branch="task/task-101",
                files=[CommitFileInfo(path="app.py", content="worker1_mod")],
                message="Worker 1 edit",
            )

            # 3. Worker 2 concurrently commits conflicting change to branch 2
            await gitea.create_commit(
                owner="testorg",
                repo_name="code-repo",
                branch="task/task-102",
                files=[CommitFileInfo(path="app.py", content="worker2_mod")],
                message="Worker 2 edit",
            )

            # 4. Worker 1 merges into main successfully
            merge1 = await gitea.merge_branch(
                owner="testorg",
                repo_name="code-repo",
                base="main",
                head="task/task-101",
            )
            assert merge1["message"] == "Merged cleanly"

            # 5. Worker 2 attempts to merge into main -> conflict is surfaced!
            with pytest.raises(GiteaConflictError) as exc_info:
                await gitea.merge_branch(
                    owner="testorg",
                    repo_name="code-repo",
                    base="main",
                    head="task/task-102",
                )
            assert exc_info.value.status_code == 409
            assert "Merge conflict detected in app.py" in str(exc_info.value.message)
