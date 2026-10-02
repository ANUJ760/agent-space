"""Temporal client configuration and service abstraction for Agent Space.

Isolates Temporal workflow orchestration behind a typed service interface:
- start_workflow(...)
- signal_workflow(...)
- query_workflow(...)
- cancel_workflow(...)
- get_workflow_status(...)
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


class MockWorkflowHandle:
    """Mock handle tracking state, signals, and queries for in-memory testing."""

    def __init__(self, workflow_id: str, workflow_name: str, arg: Any):
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.arg = arg
        self.status = "RUNNING"
        self.signals: list[tuple[str, Any]] = []
        self.state: dict[str, Any] = {"status": "RUNNING", "progress": 0}

    async def signal(self, signal_name: str, arg: Any = None) -> None:
        self.signals.append((signal_name, arg))
        if signal_name == "pause":
            self.status = "PAUSED"
            self.state["status"] = "PAUSED"
        elif signal_name == "resume":
            self.status = "RUNNING"
            self.state["status"] = "RUNNING"
        elif signal_name == "human_input":
            self.state["human_input"] = arg
            if self.status == "WAITING_FOR_HUMAN":
                self.status = "RUNNING"
                self.state["status"] = "RUNNING"
        elif signal_name == "approval":
            self.state["approval"] = arg
            if self.status == "WAITING_FOR_APPROVAL":
                self.status = "RUNNING"
                self.state["status"] = "RUNNING"
        elif signal_name == "takeover":
            self.status = "HUMAN_TAKEOVER"
            self.state["status"] = "HUMAN_TAKEOVER"
            self.state["taken_over_by"] = arg
        elif signal_name == "handoff":
            self.state["handoff"] = arg

    async def query(self, query_name: str, arg: Any = None) -> Any:
        if query_name == "status":
            return self.status
        if query_name == "state":
            return self.state
        return self.state.get(query_name)

    async def cancel(self, reason: str = "") -> None:
        self.status = "CANCELLED"
        self.state["status"] = "CANCELLED"
        self.state["cancel_reason"] = reason


class TemporalService:
    """Service abstraction isolating the Temporal SDK client."""

    def __init__(
        self,
        host: str = "localhost:7233",
        namespace: str = "default",
        task_queue: str = "agent-space-tasks",
        api_key: str | None = None,
        tls: bool = False,
    ):
        self.host = host
        self.namespace = namespace
        self.task_queue = task_queue
        self.api_key = api_key
        self.tls = tls
        self._client: Any = None
        self._is_mock = host.startswith("mock") or host.startswith("memory")
        self._mock_workflows: dict[str, MockWorkflowHandle] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to Temporal cluster or initialize mock backend."""
        if self._is_mock:
            logger.info("temporal_connected_mock", host=self.host, namespace=self.namespace)
            return

        from temporalio.client import Client

        self._client = await Client.connect(
            self.host,
            namespace=self.namespace,
            api_key=self.api_key,
            tls=self.tls,
        )
        logger.info("temporal_connected", host=self.host, namespace=self.namespace)

    async def disconnect(self) -> None:
        """Close Temporal client connection."""
        self._client = None
        self._mock_workflows.clear()
        logger.info("temporal_disconnected")

    @property
    def is_connected(self) -> bool:
        if self._is_mock:
            return True
        return self._client is not None

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Temporal is not connected")
        return self._client

    async def start_workflow(
        self,
        workflow_name: str,
        workflow_id: str,
        arg: Any = None,
        task_queue: str | None = None,
    ) -> str:
        """Start a new workflow execution. Returns workflow_id."""
        queue = task_queue or self.task_queue

        if self._is_mock:
            async with self._lock:
                existing = self._mock_workflows.get(workflow_id)
                if existing and existing.status in ("RUNNING", "PAUSED"):
                    raise RuntimeError(f"Workflow '{workflow_id}' is already running")
                handle = MockWorkflowHandle(workflow_id, workflow_name, arg)
                self._mock_workflows[workflow_id] = handle
                logger.info(
                    "temporal_mock_workflow_started",
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                )
                return workflow_id

        if self._client is None:
            await self.connect()

        handle = await self._client.start_workflow(
            workflow_name,
            arg,
            id=workflow_id,
            task_queue=queue,
        )
        return str(handle.id)

    async def signal_workflow(
        self,
        workflow_id: str,
        signal_name: str,
        arg: Any = None,
    ) -> None:
        """Send a signal to a running workflow execution."""
        if self._is_mock:
            async with self._lock:
                handle = self._mock_workflows.get(workflow_id)
                if not handle:
                    raise KeyError(f"Workflow '{workflow_id}' not found")
                await handle.signal(signal_name, arg)
                logger.info(
                    "temporal_mock_workflow_signalled",
                    workflow_id=workflow_id,
                    signal=signal_name,
                )
                return

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(workflow_id)
        await handle.signal(signal_name, arg)

    async def query_workflow(
        self,
        workflow_id: str,
        query_name: str,
        arg: Any = None,
    ) -> Any:
        """Query state from a running or completed workflow."""
        if self._is_mock:
            async with self._lock:
                handle = self._mock_workflows.get(workflow_id)
                if not handle:
                    raise KeyError(f"Workflow '{workflow_id}' not found")
                return await handle.query(query_name, arg)

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(workflow_id)
        return await handle.query(query_name, arg)

    async def cancel_workflow(
        self,
        workflow_id: str,
        reason: str = "",
    ) -> None:
        """Cancel a running workflow execution."""
        if self._is_mock:
            async with self._lock:
                handle = self._mock_workflows.get(workflow_id)
                if not handle:
                    raise KeyError(f"Workflow '{workflow_id}' not found")
                await handle.cancel(reason=reason)
                logger.info("temporal_mock_workflow_cancelled", workflow_id=workflow_id, reason=reason)
                return

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(workflow_id)
        await handle.cancel()

    async def get_workflow_status(self, workflow_id: str) -> str:
        """Fetch current status for workflow."""
        if self._is_mock:
            async with self._lock:
                handle = self._mock_workflows.get(workflow_id)
                if not handle:
                    return "NOT_FOUND"
                return handle.status

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        return str(desc.status)


_temporal_service: TemporalService | None = None


def get_temporal_service() -> TemporalService:
    """Return singleton TemporalService instance configured from application settings."""
    global _temporal_service
    if _temporal_service is None:
        from app.config import get_settings

        settings = get_settings()
        _temporal_service = TemporalService(
            host=settings.temporal_host,
            namespace=settings.temporal_namespace,
            task_queue=settings.temporal_task_queue,
            api_key=settings.temporal_api_key.get_secret_value() if settings.temporal_api_key else None,
            tls=settings.temporal_tls,
        )
    return _temporal_service


def set_temporal_service(service: TemporalService | None) -> None:
    """Set global TemporalService instance for test overrides."""
    global _temporal_service
    _temporal_service = service
