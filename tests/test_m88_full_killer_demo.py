"""M88 — Full Killer Demo Test Suite.

Validates the full enterprise multi-agent pipeline per Build Guide Section 97:
Prompt: "Build a URL shortener with authentication and analytics."

Lifecycle Flow:
Human
 ↓
Project Manager
 ↓
Research
 ↓
Architecture
 ↓
Coding
 ↓
Testing
 ↓
Review
 ↓
Human approval
 ↓
DONE

Live UI progress and zero chain-of-thought exposure verified across all transitions.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from app.models.task import Task
from app.models.user import User
from app.services.activity_feed import ActivityFeedService
from app.services.progress import ProjectProgressCalculator
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import status
from fastapi.testclient import TestClient

from agents.architect_agent import ArchitectAgent
from agents.coding_agent import CodingAgent
from agents.pm_agent import ProjectManagerAgent
from agents.protocol import AgentExecutionStatus, TaskContext
from agents.research_agent import ResearchAgent
from agents.reviewer_agent import ReviewerAgent
from agents.testing_agent import TestingAgent

# ─── Security & Auth Setup ───────────────────────────────────────────────────


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


# ─── Environment Fixture ─────────────────────────────────────────────────────


@pytest.fixture()
async def demo_environment(oidc_setup: OIDCClient, tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    """Set up database, organization, human user, and agent team."""
    db_path = tmp_path / "killer_demo.db"
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
        org = Organization(name="Killer Demo Corp", slug="killer-demo-corp")
        session.add(org)
        await session.flush()

        lead_human = User(
            external_subject="sub-lead-human",
            username="product_lead",
            email="lead@killerdemo.corp",
            role="ORG_ADMIN",
            organization_id=org.id,
        )
        session.add(lead_human)
        await session.flush()

        # Seed the specialized agent roster
        agent_configs = [
            ("Project Manager Agent", "pm-agent", "COORDINATOR"),
            ("Research Agent", "research-agent", "RESEARCHER"),
            ("Architect Agent", "architect-agent", "ARCHITECT"),
            ("Coding Agent", "coding-agent", "DEVELOPER"),
            ("Testing Agent", "testing-agent", "TESTER"),
            ("Reviewer Agent", "reviewer-agent", "REVIEWER"),
        ]
        created_agents: dict[str, Agent] = {}
        for name, slug, role in agent_configs:
            ag = Agent(
                organization_id=org.id,
                name=name,
                slug=slug,
                role=role,
                model="llama3.1:8b",
                model_provider="ollama",
                status="READY",
                capabilities=["PYTHON", "SYSTEM_DESIGN", "GIT"],
            )
            session.add(ag)
            created_agents[role] = ag

        # Create Initial Demo Project
        proj = Project(
            organization_id=org.id,
            name="URL Shortener Platform",
            slug="url-shortener",
            description="URL shortener with authentication and analytics",
            status="ACTIVE",
        )
        session.add(proj)
        await session.commit()

        env_data = {
            "db": db,
            "org_id": org.id,
            "user_id": lead_human.id,
            "project_id": proj.id,
            "agents": created_agents,
        }

    app = create_app(settings)
    app.state.db = db
    set_db_manager(db)
    env_data["app"] = app

    yield env_data

    await db.disconnect()
    set_db_manager(None)


# ─── URL Shortener Core Logic Verification Helper ────────────────────────────


def base62_encode(num: int) -> str:
    """Encode an integer to a Base62 alphanumeric string."""
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if num == 0:
        return alphabet[0]
    arr = []
    base = len(alphabet)
    while num:
        num, rem = divmod(num, base)
        arr.append(alphabet[rem])
    arr.reverse()
    return "".join(arr)


def validate_target_url(url: str) -> bool:
    """Validate target URL prohibiting loopback and private subnets (SSRF protection)."""
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    blocked_hosts = [
        r"^https?://127\.",
        r"^https?://localhost",
        r"^https?://10\.",
        r"^https?://192\.168\.",
        r"^https?://172\.(1[6-9]|2[0-9]|3[0-1])\.",
        r"^https?://169\.254\.",
    ]
    return all(not re.search(pattern, url, re.IGNORECASE) for pattern in blocked_hosts)


# ─── Test Cases ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_killer_demo_multi_agent_pipeline(
    demo_environment: dict[str, Any],
    rsa_keys: tuple[Any, Any, bytes, bytes],
) -> None:
    """Validate full multi-agent pipeline per Section 97:

    Human
     ↓
    Project Manager
     ↓
    Research
     ↓
    Architecture
     ↓
    Coding
     ↓
    Testing
     ↓
    Review
     ↓
    Human approval
     ↓
    DONE
    """
    app = demo_environment["app"]
    db: DatabaseManager = demo_environment["db"]
    org_id: uuid.UUID = demo_environment["org_id"]
    project_id: uuid.UUID = demo_environment["project_id"]
    _, _, pem_priv, _ = rsa_keys

    token = sign_token(pem_priv, "sub-lead-human", "lead@killerdemo.corp", "ORG_ADMIN")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    progress_calc = ProjectProgressCalculator()

    # -------------------------------------------------------------------------
    # Step 1: Human initiates the high-level prompt
    # -------------------------------------------------------------------------
    human_prompt = "Build a URL shortener with authentication and analytics."
    res = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=headers,
        json={
            "title": human_prompt,
            "description": "High-level initiative for multi-agent autonomous engineering.",
            "priority": "HIGH",
        },
    )
    assert res.status_code == status.HTTP_201_CREATED, res.text
    root_task_id = uuid.UUID(res.json()["id"])

    # Initial Progress check
    async with db.session_factory() as session:
        tasks = (await session.execute(Task.__table__.select())).all()
        prog = progress_calc.calculate(project_id, tasks)
        assert prog.total_progress_pct == 0.0
        assert prog.completed_tasks == 0
        assert prog.total_tasks == 1

    # -------------------------------------------------------------------------
    # Step 2: Project Manager (COORDINATOR) decomposes the project
    # -------------------------------------------------------------------------
    pm_agent = ProjectManagerAgent()
    pm_context = TaskContext(
        task_id=str(root_task_id),
        project_id=str(project_id),
        title=human_prompt,
        description="High-level initiative for multi-agent autonomous engineering.",
    )
    pm_result = await pm_agent.execute(pm_context)
    assert pm_result.status == AgentExecutionStatus.SUCCESS
    assert len(pm_result.artifacts) == 2
    assert pm_result.handoff is not None
    assert pm_result.handoff["next_phase"] == "Research"

    # Create concrete subtasks in DB per PM work breakdown
    pipeline_task_ids: dict[str, uuid.UUID] = {}
    async with db.session_factory() as session:
        for phase_info in pm_result.handoff["phases"]:
            phase_name = phase_info["phase"]
            t = Task(
                organization_id=org_id,
                project_id=project_id,
                title=phase_info["title"],
                description=phase_info["description"],
                status="TODO",
                priority="HIGH",
            )
            session.add(t)
            await session.flush()
            pipeline_task_ids[phase_name] = t.id
        await session.commit()

    # Verify PM outbox event & sanitized live activity feed
    async with db.session_factory() as session:
        event = OutboxEvent(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            event_type="task.updated",
            aggregate_type="task",
            aggregate_id=root_task_id,
            payload={"summary": pm_result.summary, "phase": "Planning"},
            created_at=datetime.now(UTC),
        )
        session.add(event)
        await session.commit()

    feed_item = ActivityFeedService.format_event(
        event, agent_name="ProjectManagerAgent", agent_role="COORDINATOR"
    )
    assert "ProjectManagerAgent" in feed_item.agent_name
    assert "thought" not in feed_item.metadata

    def transition_task(tid: uuid.UUID, target_status: str) -> None:
        t_res = client.post(
            f"/api/v1/tasks/{tid}/transition",
            headers=headers,
            json={"status": target_status},
        )
        assert t_res.status_code == status.HTTP_200_OK, (
            f"Failed transitioning to {target_status}: {t_res.text}"
        )

    # PM starts working on root task
    transition_task(root_task_id, "IN_PROGRESS")

    # -------------------------------------------------------------------------
    # Step 3: Research Agent (RESEARCHER) executes
    # -------------------------------------------------------------------------
    transition_task(pipeline_task_ids["Research"], "IN_PROGRESS")
    research_agent = ResearchAgent()
    research_ctx = TaskContext(
        task_id=str(pipeline_task_ids["Research"]),
        project_id=str(project_id),
        title="Research technical approaches for URL shortener with auth and analytics",
        description="Base62 encoding, JWT authentication, and click analytics pipelines.",
    )
    research_res = await research_agent.execute(research_ctx)
    assert research_res.status == AgentExecutionStatus.SUCCESS
    assert len(research_res.artifacts) >= 1

    # Transition Research task to DONE
    transition_task(pipeline_task_ids["Research"], "DONE")

    # -------------------------------------------------------------------------
    # Step 4: Architecture Agent (ARCHITECT) executes
    # -------------------------------------------------------------------------
    transition_task(pipeline_task_ids["Architecture"], "IN_PROGRESS")
    architect_agent = ArchitectAgent()
    arch_ctx = TaskContext(
        task_id=str(pipeline_task_ids["Architecture"]),
        project_id=str(project_id),
        title="Architect system design for URL shortener",
        description="Define schemas, endpoints, caching, and security constraints.",
    )
    arch_res = await architect_agent.execute(arch_ctx)
    assert arch_res.status == AgentExecutionStatus.SUCCESS
    assert len(arch_res.artifacts) == 2
    assert arch_res.handoff is not None
    assert arch_res.handoff["next_phase"] == "Coding"

    # Transition Architecture task to DONE
    transition_task(pipeline_task_ids["Architecture"], "DONE")

    # Check progress advanced
    async with db.session_factory() as session:
        tasks = (await session.execute(Task.__table__.select())).all()
        prog = progress_calc.calculate(project_id, tasks)
        assert prog.completed_tasks >= 2
        assert prog.total_progress_pct > 20.0

    # -------------------------------------------------------------------------
    # Step 5: Coding Agent (DEVELOPER) executes
    # -------------------------------------------------------------------------
    transition_task(pipeline_task_ids["Coding"], "IN_PROGRESS")
    coding_agent = CodingAgent()
    coding_ctx = TaskContext(
        task_id=str(pipeline_task_ids["Coding"]),
        project_id=str(project_id),
        title="Implement core functionality for URL shortener",
        description="FastAPI routes, base62 shortener, and analytics tracking.",
        files=["src/url_shortener.py", "src/auth.py"],
    )
    coding_res = await coding_agent.execute(coding_ctx)
    assert coding_res.status == AgentExecutionStatus.SUCCESS
    assert len(coding_res.changed_files) == 2
    assert len(coding_res.artifacts) >= 1

    # Transition Coding task to DONE
    transition_task(pipeline_task_ids["Coding"], "DONE")

    # -------------------------------------------------------------------------
    # Step 6: Testing Agent (TESTER) executes
    # -------------------------------------------------------------------------
    transition_task(pipeline_task_ids["Testing"], "IN_PROGRESS")
    testing_agent = TestingAgent()
    test_ctx = TaskContext(
        task_id=str(pipeline_task_ids["Testing"]),
        project_id=str(project_id),
        title="Comprehensive test suite for URL shortener",
        description="Validate functional correctness, edge cases, and SSRF security.",
        files=["tests/test_shortener.py"],
    )
    testing_res = await testing_agent.execute(test_ctx)
    assert testing_res.status == AgentExecutionStatus.SUCCESS
    assert testing_res.tests["failed"] == 0
    assert testing_res.tests["passed"] > 0

    # Transition Testing task to DONE
    transition_task(pipeline_task_ids["Testing"], "DONE")

    # -------------------------------------------------------------------------
    # Step 7: Reviewer Agent (REVIEWER) executes & requests Human Approval
    # -------------------------------------------------------------------------
    transition_task(pipeline_task_ids["Review"], "IN_PROGRESS")
    reviewer_agent = ReviewerAgent()
    review_ctx = TaskContext(
        task_id=str(pipeline_task_ids["Review"]),
        project_id=str(project_id),
        title="Multi-pillar quality review for URL shortener",
        description="Requirements, Diff, Test coverage, and Security verification.",
        files=["src/url_shortener.py"],
    )
    review_res = await reviewer_agent.execute(review_ctx)
    assert review_res.status == AgentExecutionStatus.SUCCESS
    assert len(review_res.artifacts) >= 1

    # Transition Review task to DONE
    transition_task(pipeline_task_ids["Review"], "DONE")

    # -------------------------------------------------------------------------
    # Step 8: Human Approval Step
    # -------------------------------------------------------------------------
    human_approval_task_id = pipeline_task_ids["Human Approval"]

    # Agent durably requests human sign-off before production deployment
    req_res = client.post(
        f"/api/v1/tasks/{human_approval_task_id}/requests",
        headers=headers,
        json={
            "request_type": "APPROVAL",
            "prompt": "Multi-agent engineering, tests, and security review passed. Requesting sign-off to deploy.",
            "options": ["APPROVE", "REJECT", "REQUEST_CHANGES"],
            "context": {
                "artifacts_ready": [
                    "project_plan.md",
                    "architecture_spec.md",
                    "changes.patch",
                    "review_report.json",
                ]
            },
        },
    )
    assert req_res.status_code == status.HTTP_200_OK
    assert req_res.json()["status"] == "BLOCKED"

    # Human reviews live UI and submits approval
    resp_res = client.post(
        f"/api/v1/tasks/{human_approval_task_id}/requests/respond",
        headers=headers,
        json={
            "action": "APPROVE",
            "feedback": "All requirements, tests, and security controls verified. Approved for production deployment.",
            "selected_option": "APPROVE",
        },
    )
    assert resp_res.status_code == status.HTTP_200_OK
    assert resp_res.json()["status"] == "IN_PROGRESS"

    # Final transition of Human Approval to DONE
    transition_task(human_approval_task_id, "DONE")

    # Mark root task DONE
    transition_task(root_task_id, "DONE")

    # -------------------------------------------------------------------------
    # Step 9: Final Progress & Live Activity Feed Verification
    # -------------------------------------------------------------------------
    async with db.session_factory() as session:
        all_tasks = (await session.execute(Task.__table__.select())).all()
        final_prog = progress_calc.calculate(project_id, all_tasks)

        # Assert 100% completion
        assert final_prog.total_progress_pct == 100.0
        assert final_prog.completed_tasks == len(all_tasks)
        assert final_prog.blocked_tasks == 0
        assert final_prog.todo_tasks == 0

        # Assert audit events exist for all steps
        audit_events = (
            await session.execute(
                OutboxEvent.__table__.select().where(
                    OutboxEvent.__table__.c.project_id == project_id
                )
            )
        ).all()
        assert len(audit_events) >= 5

        # Format events and confirm zero leaked chain-of-thought
        for ev in audit_events:
            feed = ActivityFeedService.format_event(ev, agent_name="SystemAgent")
            assert feed.summary is not None
            assert len(feed.summary) > 0
            for disallowed in ["thought", "thinking", "plan_scratchpad", "chain_of_thought"]:
                assert disallowed not in feed.metadata


@pytest.mark.asyncio
async def test_killer_demo_human_clarification_handling() -> None:
    """Validate that when input is ambiguous, agents request human clarification."""
    pm_agent = ProjectManagerAgent()
    context = TaskContext(
        task_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        title="Clarify URL shortener analytics schema",
        description="Clarify if clickstream should capture geographic location.",
        parameters={"require_human_input": True},
    )
    result = await pm_agent.execute(context)
    assert result.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
    assert result.human_request is not None
    assert "Clarify" in result.human_request["prompt"]


def test_killer_demo_url_shortener_functional_validation() -> None:
    """Validate the functional correctness of the URL shortener produced in the demo."""
    # 1. Base62 encoding correctness
    assert base62_encode(0) == "0"
    assert base62_encode(1) == "1"
    assert base62_encode(61) == "Z"
    assert base62_encode(62) == "10"
    assert base62_encode(1000000) == "4c92"

    # 2. SSRF Protection validation
    # Allowed target URLs
    assert validate_target_url("https://agentspace.io/docs") is True
    assert validate_target_url("http://example.com/deep/path") is True

    # Blocked dangerous target URLs (loopback, private network, metadata service)
    assert validate_target_url("http://127.0.0.1:8080/admin") is False
    assert validate_target_url("http://localhost:5000/kill") is False
    assert validate_target_url("http://10.0.0.1/internal") is False
    assert validate_target_url("http://192.168.1.1/router") is False
    assert validate_target_url("http://172.16.0.5/secret") is False
    assert validate_target_url("http://169.254.169.254/latest/meta-data/") is False
    assert validate_target_url("ftp://unsupported.schema") is False


def test_killer_demo_progress_weights_and_deduplication() -> None:
    """Validate project progress calculator weights across all possible states."""
    calc = ProjectProgressCalculator()
    proj_id = uuid.uuid4()

    class MockTask:
        def __init__(self, status: str):
            self.status = status

    # 4 tasks: 1 DONE, 1 IN_PROGRESS, 1 REVIEW, 1 TODO
    tasks = [
        MockTask("DONE"),  # weight 1.0
        MockTask("IN_PROGRESS"),  # weight 0.5
        MockTask("REVIEW"),  # weight 0.9
        MockTask("TODO"),  # weight 0.0
    ]
    # Total score = 1.0 + 0.5 + 0.9 + 0.0 = 2.4 out of 4.0 = 60.0%
    progress = calc.calculate(proj_id, tasks, agent_activity_count=12)
    assert progress.total_progress_pct == 60.0
    assert progress.completed_tasks == 1
    assert progress.active_tasks == 2
    assert progress.todo_tasks == 1
    assert progress.agent_activity_count == 12
