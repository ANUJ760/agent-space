"""Tests for M28 — Temporal Client.

Validates:
- TemporalService lifecycle
- start_workflow returns workflow_id
- query_workflow returns current execution state
- signal_workflow sends signals to running workflow
- cancel_workflow updates status to CANCELLED
- Error handling on non-existent workflow handles
"""

import pytest
from app.temporal.client import TemporalService


@pytest.fixture()
async def temporal_service() -> TemporalService:
    service = TemporalService(host="mock://temporal", namespace="test-ns")
    await service.connect()
    try:
        yield service
    finally:
        await service.disconnect()


class TestTemporalClient:
    async def test_start_and_query_workflow(self, temporal_service: TemporalService) -> None:
        wf_id = "wf-task-101"
        started_id = await temporal_service.start_workflow(
            workflow_name="TaskWorkflow",
            workflow_id=wf_id,
            arg={"task_id": "101"},
        )
        assert started_id == wf_id

        # Query status
        status = await temporal_service.get_workflow_status(wf_id)
        assert status == "RUNNING"

        # Query state
        state = await temporal_service.query_workflow(wf_id, "state")
        assert state["status"] == "RUNNING"
        assert state["progress"] == 0

    async def test_signal_workflow(self, temporal_service: TemporalService) -> None:
        wf_id = "wf-task-102"
        await temporal_service.start_workflow("TaskWorkflow", wf_id)

        # Send pause signal
        await temporal_service.signal_workflow(wf_id, "pause")
        status = await temporal_service.get_workflow_status(wf_id)
        assert status == "PAUSED"

        # Send resume signal
        await temporal_service.signal_workflow(wf_id, "resume")
        status = await temporal_service.get_workflow_status(wf_id)
        assert status == "RUNNING"

    async def test_cancel_workflow(self, temporal_service: TemporalService) -> None:
        wf_id = "wf-task-103"
        await temporal_service.start_workflow("TaskWorkflow", wf_id)

        await temporal_service.cancel_workflow(wf_id, reason="User requested cancellation")
        status = await temporal_service.get_workflow_status(wf_id)
        assert status == "CANCELLED"

        state = await temporal_service.query_workflow(wf_id, "state")
        assert state["cancel_reason"] == "User requested cancellation"

    async def test_query_missing_workflow_raises(self, temporal_service: TemporalService) -> None:
        with pytest.raises(KeyError):
            await temporal_service.query_workflow("non-existent-wf", "state")
