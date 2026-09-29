"""Tests for M30 — TaskWorkflow & Task Activities.

Validates:
- load_task_activity
- validate_dependencies_activity
- claim_task_activity
- execute_worker_activity
- finish_task_activity
- TaskWorkflow structure and state query
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.config import Settings
from app.database import DatabaseManager, set_db_manager
from app.models.agent import Agent
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.task_dependency import TaskDependency
from app.temporal.activities.task_activities import (
    claim_task_activity,
    execute_worker_activity,
    finish_task_activity,
    load_task_activity,
    validate_dependencies_activity,
)
from app.temporal.workflows.task_workflow import TaskWorkflow


@pytest.fixture()
async def workflow_db(tmp_path: Path) -> AsyncIterator[tuple[DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID]]:
    db_path = tmp_path / "wf_test.db"
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
        org = Organization(name="WF Org", slug="wf-org")
        session.add(org)
        await session.flush()

        proj = Project(organization_id=org.id, name="WF Project", slug="wf-project")
        session.add(proj)
        await session.flush()

        agent = Agent(
            organization_id=org.id,
            project_id=proj.id,
            name="Coder Agent",
            slug="coder-agent",
            role="DEVELOPER",
        )
        session.add(agent)
        await session.flush()

        task = Task(
            organization_id=org.id,
            project_id=proj.id,
            title="Implement Task Workflow",
            priority="HIGH",
            status="TODO",
        )
        session.add(task)
        await session.commit()

        yield db, org.id, proj.id, task.id

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]


class TestTaskActivities:
    async def test_load_task_activity(
        self,
        workflow_db: tuple[DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _, _, _, task_id = workflow_db
        task_data = await load_task_activity(str(task_id))
        assert task_data["id"] == str(task_id)
        assert task_data["title"] == "Implement Task Workflow"
        assert task_data["status"] == "TODO"

    async def test_validate_dependencies_activity_no_deps(
        self,
        workflow_db: tuple[DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _, _, _, task_id = workflow_db
        res = await validate_dependencies_activity(str(task_id))
        assert res["valid"] is True
        assert len(res["unmet_dependencies"]) == 0

    async def test_validate_dependencies_activity_unmet(
        self,
        workflow_db: tuple[DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        db, org_id, proj_id, task_id = workflow_db

        # Create upstream task that is still in TODO
        async with db.session_factory() as session:
            upstream_task = Task(
                organization_id=org_id,
                project_id=proj_id,
                title="Upstream Task",
                priority="MEDIUM",
                status="TODO",
            )
            session.add(upstream_task)
            await session.flush()

            dep = TaskDependency(
                task_id=task_id,
                depends_on_task_id=upstream_task.id,
            )
            session.add(dep)
            await session.commit()

        res = await validate_dependencies_activity(str(task_id))
        assert res["valid"] is False
        assert str(upstream_task.id) in res["unmet_dependencies"]

    async def test_claim_and_execute_and_finish_flow(
        self,
        workflow_db: tuple[DatabaseManager, uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        db, org_id, proj_id, _ = workflow_db

        # Create fresh task and agent
        async with db.session_factory() as session:
            agent = Agent(
                organization_id=org_id,
                project_id=proj_id,
                name="Worker Agent",
                slug=f"worker-agent-{uuid.uuid4().hex[:6]}",
                role="DEVELOPER",
            )
            session.add(agent)
            await session.flush()

            task = Task(
                organization_id=org_id,
                project_id=proj_id,
                title="Fresh Task for Flow",
                status="TODO",
            )
            session.add(task)
            await session.commit()

            task_id_str = str(task.id)
            agent_id_str = str(agent.id)

        # 1. Claim
        claim_res = await claim_task_activity(
            {
                "task_id": task_id_str,
                "agent_id": agent_id_str,
                "expected_version": 1,
            }
        )
        assert claim_res["status"] == "CLAIMED"
        assert claim_res["assigned_agent_id"] == agent_id_str

        # 2. Execute worker
        exec_res = await execute_worker_activity(
            {
                "task_id": task_id_str,
                "agent_id": agent_id_str,
            }
        )
        assert exec_res["status"] == "REVIEW"

        # 3. Finish
        finish_res = await finish_task_activity(task_id_str)
        assert finish_res["status"] == "DONE"

    async def test_task_workflow_initial_state(self) -> None:
        wf = TaskWorkflow()
        state = wf.state()
        assert state["status"] == "INITIALIZED"
        assert state["step"] == "INIT"
