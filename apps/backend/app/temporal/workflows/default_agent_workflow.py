"""Temporal workflow for the shared default agent; BYOK inference stays in browsers."""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.default_agent import (
        execute_default_agent_task,
        fail_default_agent_task,
    )


@workflow.defn
class DefaultAgentTaskWorkflow:
    def __init__(self) -> None:
        self._status = "QUEUED"

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.run
    async def run(self, payload: dict[str, str]) -> dict[str, Any]:
        self._status = "RUNNING"
        try:
            result = await workflow.execute_activity(
                execute_default_agent_task,
                payload,
                start_to_close_timeout=timedelta(minutes=12),
                heartbeat_timeout=timedelta(minutes=4),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:
            self._status = "FAILED"
            await workflow.execute_activity(
                fail_default_agent_task,
                {"task_id": payload["task_id"], "error": str(exc)[:2048]},
                start_to_close_timeout=timedelta(seconds=30),
            )
            raise
        self._status = "REVIEW"
        return dict(result)
