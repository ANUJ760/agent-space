"""TaskWorkflow orchestrating end-to-end task execution in Temporal."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.task_activities import (
        claim_task_activity,
        execute_worker_activity,
        finish_task_activity,
        load_task_activity,
        validate_dependencies_activity,
    )


@workflow.defn
class TaskWorkflow:
    """Durable workflow orchestrating task execution:

    load task -> validate dependencies -> claim -> execute worker -> finish
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "status": "INITIALIZED",
            "step": "INIT",
            "task_id": None,
            "agent_id": None,
            "error": None,
        }

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        task_id = input_data["task_id"]
        agent_id = input_data["agent_id"]
        self._state["task_id"] = task_id
        self._state["agent_id"] = agent_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=10),
            maximum_attempts=3,
        )

        # 1. Load task
        self._state["step"] = "LOAD_TASK"
        self._state["status"] = "RUNNING"
        task_info = await workflow.execute_activity(
            load_task_activity,
            task_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry_policy,
        )

        # 2. Validate dependencies
        self._state["step"] = "VALIDATE_DEPENDENCIES"
        dep_check = await workflow.execute_activity(
            validate_dependencies_activity,
            task_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry_policy,
        )
        if not dep_check["valid"]:
            self._state["status"] = "BLOCKED"
            self._state["error"] = f"Unmet dependencies: {dep_check['unmet_dependencies']}"
            return self._state

        # 3. Claim task
        self._state["step"] = "CLAIM"
        claim_res = await workflow.execute_activity(
            claim_task_activity,
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "expected_version": task_info["version"],
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry_policy,
        )

        # 4. Execute worker
        self._state["step"] = "EXECUTE_WORKER"
        worker_res = await workflow.execute_activity(
            execute_worker_activity,
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "version": claim_res["version"],
            },
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        self._state["worker_output"] = worker_res

        # 5. Finish
        self._state["step"] = "FINISH"
        finish_res = await workflow.execute_activity(
            finish_task_activity,
            task_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry_policy,
        )

        self._state["status"] = "COMPLETED"
        self._state["result"] = finish_res
        return self._state

    @workflow.query
    def state(self) -> dict[str, Any]:
        """Query workflow state and current execution step."""
        return self._state
