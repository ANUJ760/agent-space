"""TaskWorkflow orchestrating end-to-end task execution in Temporal with durable signals."""

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
    """Durable workflow orchestrating task execution with human-in-the-loop signals:

    - Signals: pause, resume, human_input, approval, takeover, handoff
    - Durable non-polling wait conditions
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "status": "INITIALIZED",
            "step": "INIT",
            "task_id": None,
            "agent_id": None,
            "error": None,
            "paused": False,
            "human_input": None,
            "approval": None,
            "taken_over_by": None,
            "handoff": None,
        }
        self._paused: bool = False
        self._human_input: dict[str, Any] | None = None
        self._approval: dict[str, Any] | None = None
        self._taken_over_by: str | None = None

    # --------------------------------------------------------------------------
    # Signals
    # --------------------------------------------------------------------------

    @workflow.signal
    def pause(self) -> None:
        """Signal workflow to pause execution."""
        self._paused = True
        self._state["paused"] = True
        self._state["status"] = "PAUSED"

    @workflow.signal
    def resume(self) -> None:
        """Signal paused workflow to resume execution."""
        self._paused = False
        self._state["paused"] = False
        self._state["status"] = "RUNNING"

    @workflow.signal
    def human_input(self, payload: dict[str, Any]) -> None:
        """Signal providing requested human input to the workflow."""
        self._human_input = payload
        self._state["human_input"] = payload
        if self._state["status"] == "WAITING_FOR_HUMAN":
            self._state["status"] = "RUNNING"

    @workflow.signal
    def approval(self, approved: bool, reason: str = "") -> None:
        """Signal providing approval or rejection for review step."""
        self._approval = {"approved": approved, "reason": reason}
        self._state["approval"] = self._approval
        if self._state["status"] == "WAITING_FOR_APPROVAL":
            self._state["status"] = "RUNNING"

    @workflow.signal
    def takeover(self, user_id: str) -> None:
        """Signal human takeover of task execution."""
        self._taken_over_by = user_id
        self._state["taken_over_by"] = user_id
        self._state["status"] = "HUMAN_TAKEOVER"

    @workflow.signal
    def handoff(self, payload: dict[str, Any]) -> None:
        """Signal task handoff to another agent or person."""
        self._state["handoff"] = payload
        to_id = payload.get("to_entity_id")
        if to_id:
            self._state["agent_id"] = to_id

    # --------------------------------------------------------------------------
    # Queries
    # --------------------------------------------------------------------------

    @workflow.query
    def state(self) -> dict[str, Any]:
        """Query complete workflow state."""
        return self._state

    @workflow.query
    def is_paused(self) -> bool:
        """Query if workflow is currently paused."""
        return self._paused

    @workflow.query
    def pending_human_input(self) -> dict[str, Any] | None:
        """Query pending human input request if waiting."""
        if self._state["status"] == "WAITING_FOR_HUMAN":
            return self._state.get("human_prompt")
        return None

    # --------------------------------------------------------------------------
    # Main Workflow Execution
    # --------------------------------------------------------------------------

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        task_id = input_data["task_id"]
        agent_id = input_data["agent_id"]
        require_approval = input_data.get("require_approval", False)

        self._state["task_id"] = task_id
        self._state["agent_id"] = agent_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=10),
            maximum_attempts=3,
        )

        # Durable pause check helper
        async def check_pause() -> None:
            if self._paused:
                await workflow.wait_condition(lambda: not self._paused)

        await check_pause()

        # 1. Load task
        self._state["step"] = "LOAD_TASK"
        self._state["status"] = "RUNNING"
        task_info = await workflow.execute_activity(
            load_task_activity,
            task_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry_policy,
        )

        await check_pause()

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

        await check_pause()

        # 3. Claim task
        self._state["step"] = "CLAIM"
        claim_res = await workflow.execute_activity(
            claim_task_activity,
            {
                "task_id": task_id,
                "agent_id": self._state["agent_id"],
                "expected_version": task_info["version"],
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry_policy,
        )

        await check_pause()

        # 4. Execute worker
        self._state["step"] = "EXECUTE_WORKER"
        worker_res = await workflow.execute_activity(
            execute_worker_activity,
            {
                "task_id": task_id,
                "agent_id": self._state["agent_id"],
                "version": claim_res["version"],
            },
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        self._state["worker_output"] = worker_res

        await check_pause()

        # If approval required, wait durably for approval signal
        if require_approval:
            self._state["status"] = "WAITING_FOR_APPROVAL"
            await workflow.wait_condition(lambda: self._approval is not None)
            approval = self._approval or {}
            if not approval.get("approved"):
                self._state["status"] = "REJECTED"
                self._state["error"] = f"Rejected: {approval.get('reason')}"
                return self._state

        await check_pause()

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
