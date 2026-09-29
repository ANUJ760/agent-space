"""Temporal Worker Infrastructure for Agent Space.

Manages worker lifecycle, task queues, logging, and metrics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class WorkerConfig:
    """Configuration options for a Temporal Worker."""

    task_queue: str = "agent-space-tasks"
    max_concurrent_activities: int = 100
    max_concurrent_workflow_tasks: int = 100
    workflows: list[type] = field(default_factory=list)
    activities: list[Any] = field(default_factory=list)


class WorkerManager:
    """Manages worker lifecycle, registration, and shutdown."""

    def __init__(self, config: WorkerConfig):
        self.config = config
        self._worker: Any = None
        self._state: str = "STOPPED"
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> str:
        return self._state

    async def initialize(self, client: Any) -> None:
        """Initialize Temporal worker instance with registered workflows and activities."""
        from temporalio.worker import Worker

        from app.temporal.activities import ping_activity, trivial_activity
        from app.temporal.workflows import TrivialTestWorkflow

        workflows = self.config.workflows or [TrivialTestWorkflow]
        activities = self.config.activities or [trivial_activity, ping_activity]

        self._worker = Worker(
            client,
            task_queue=self.config.task_queue,
            workflows=workflows,
            activities=activities,
            max_concurrent_activities=self.config.max_concurrent_activities,
            max_concurrent_workflow_tasks=self.config.max_concurrent_workflow_tasks,
        )
        logger.info(
            "temporal_worker_initialized",
            task_queue=self.config.task_queue,
            workflows=[w.__name__ for w in workflows],
            activities=[getattr(a, "__name__", str(a)) for a in activities],
        )

    async def start(self) -> None:
        """Start worker execution in background."""
        async with self._lock:
            if self._worker is None:
                raise RuntimeError("Worker not initialized. Call initialize(client) first.")
            self._state = "RUNNING"
            self._task = asyncio.create_task(self._worker.run())
            logger.info("temporal_worker_started", task_queue=self.config.task_queue)

    async def shutdown(self) -> None:
        """Gracefully stop worker."""
        import contextlib

        async with self._lock:
            self._state = "STOPPING"
            if self._worker is not None and self._task and not self._task.done():
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            self._state = "STOPPED"
            logger.info("temporal_worker_shutdown_complete")
