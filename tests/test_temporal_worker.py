"""Tests for M29 — Temporal Worker Infrastructure.

Validates:
- Activity execution: trivial_activity and ping_activity
- Worker configuration validation
- WorkerManager lifecycle management (initialize, start, shutdown)
- TrivialTestWorkflow structure and status query
"""

from unittest.mock import AsyncMock, MagicMock

from app.temporal.activities.test_activity import ping_activity, trivial_activity
from app.temporal.workers.worker import WorkerConfig, WorkerManager
from app.temporal.workflows.test_workflow import TrivialTestWorkflow


class TestTemporalActivities:
    async def test_trivial_activity(self) -> None:
        res = await trivial_activity("hello-temporal")
        assert res == "processed:hello-temporal"

    async def test_ping_activity(self) -> None:
        payload = {"agent": "coder-1", "action": "inspect"}
        res = await ping_activity(payload)
        assert res["status"] == "ok"
        assert res["echo"] == payload


class TestTemporalWorkerInfrastructure:
    async def test_worker_config_defaults(self) -> None:
        config = WorkerConfig(task_queue="custom-queue")
        assert config.task_queue == "custom-queue"
        assert config.max_concurrent_activities == 100
        assert config.max_concurrent_workflow_tasks == 100

    async def test_worker_manager_lifecycle(self) -> None:
        from unittest.mock import patch

        config = WorkerConfig(task_queue="test-queue")
        manager = WorkerManager(config)
        assert manager.state == "STOPPED"

        with patch("temporalio.worker.Worker") as mock_worker_cls:
            mock_worker_instance = MagicMock()
            mock_worker_instance.run = AsyncMock()
            mock_worker_cls.return_value = mock_worker_instance

            mock_client = MagicMock()
            await manager.initialize(mock_client)
            assert manager._worker is not None

            await manager.start()
            assert manager.state == "RUNNING"

            await manager.shutdown()
            assert manager.state == "STOPPED"

    async def test_workflow_definition(self) -> None:
        wf = TrivialTestWorkflow()
        assert wf.status() == "INITIALIZED"
