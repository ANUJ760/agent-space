"""Tests for M32 — Workflow Recovery, Retries, Timeouts, and Heartbeats.

Validates:
- RetryPolicy construction with exponential backoff and error filters
- Activity heartbeat helper execution
- Failure recovery activity (handle_task_failure_activity)
- Worker crash simulation: activity failure on attempt 1 with recovery on retry
"""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from app.config import Settings
from app.database import DatabaseManager, set_db_manager
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.temporal.activities.task_activities import handle_task_failure_activity
from app.temporal.policies import (
    WorkflowTimeouts,
    get_default_retry_policy,
    send_activity_heartbeat,
)


@pytest.fixture()
async def recovery_db(tmp_path: Path) -> AsyncIterator[tuple[DatabaseManager, uuid.UUID, uuid.UUID]]:
    db_path = tmp_path / "recovery_test.db"
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
        org = Organization(name="Recovery Org", slug="recovery-org")
        session.add(org)
        await session.flush()

        proj = Project(organization_id=org.id, name="Recovery Proj", slug="recovery-proj")
        session.add(proj)
        await session.flush()

        task = Task(
            organization_id=org.id,
            project_id=proj.id,
            title="Task for Crash Recovery",
            status="IN_PROGRESS",
        )
        session.add(task)
        await session.commit()

        yield db, org.id, task.id

    await db.disconnect()
    set_db_manager(None)  # type: ignore[arg-type]


class TestWorkflowPoliciesAndTimeouts:
    def test_retry_policy_defaults(self) -> None:
        policy = get_default_retry_policy(max_attempts=5)
        assert policy.maximum_attempts == 5
        assert policy.backoff_coefficient == 2.0
        assert policy.initial_interval == timedelta(seconds=1)
        assert "ValueError" in (policy.non_retryable_error_types or [])

    def test_workflow_timeouts_config(self) -> None:
        timeouts = WorkflowTimeouts()
        assert timeouts.start_to_close == timedelta(minutes=5)
        assert timeouts.schedule_to_close == timedelta(minutes=15)
        assert timeouts.heartbeat_timeout == timedelta(seconds=30)

    async def test_send_activity_heartbeat(self) -> None:
        # Outside active Temporal activity context, should safely log and not raise
        await send_activity_heartbeat(step_name="compile_code", progress=50, details={"lines": 200})


class TestWorkflowRecoveryActivities:
    async def test_handle_task_failure_blocked(
        self,
        recovery_db: tuple[DatabaseManager, uuid.UUID, uuid.UUID],
    ) -> None:
        _, _, task_id = recovery_db

        res = await handle_task_failure_activity(
            {
                "task_id": str(task_id),
                "error_message": "LLM generation timeout after 300s",
                "reset_to_todo": False,
            }
        )
        assert res["status"] == "BLOCKED"
        assert res["error_message"] == "LLM generation timeout after 300s"

    async def test_handle_task_failure_reset_to_todo(
        self,
        recovery_db: tuple[DatabaseManager, uuid.UUID, uuid.UUID],
    ) -> None:
        _, _, task_id = recovery_db

        res = await handle_task_failure_activity(
            {
                "task_id": str(task_id),
                "error_message": "Worker node evaporated; resetting to queue",
                "reset_to_todo": True,
            }
        )
        assert res["status"] == "TODO"


class TestWorkerCrashSimulation:
    async def test_simulated_crash_and_retry_recovery(self) -> None:
        attempts = 0

        async def flaky_worker_activity() -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                # Simulate worker process segmentation fault / crash on first attempt
                raise RuntimeError("Worker process crash (SIGSEGV / OOM simulated)")
            return "recovered_on_retry"

        # Execute under retry loop simulating Temporal's retry policy
        policy = get_default_retry_policy(max_attempts=3)
        result = None
        for current_attempt in range(1, (policy.maximum_attempts or 3) + 1):
            try:
                result = await flaky_worker_activity()
                break
            except Exception as exc:
                if current_attempt >= (policy.maximum_attempts or 3):
                    raise exc

        assert result == "recovered_on_retry"
        assert attempts == 2
