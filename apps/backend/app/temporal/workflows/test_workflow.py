"""Test workflow for verifying worker infrastructure."""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.test_activity import trivial_activity


@workflow.defn
class TrivialTestWorkflow:
    """Trivial test workflow executing trivial_activity."""

    def __init__(self) -> None:
        self._status = "INITIALIZED"

    @workflow.run
    async def run(self, input_str: str) -> str:
        self._status = "RUNNING"
        res = await workflow.execute_activity(
            trivial_activity,
            input_str,
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._status = "COMPLETED"
        return res

    @workflow.query
    def status(self) -> str:
        return self._status
