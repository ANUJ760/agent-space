"""Retry policies, activity timeouts, heartbeat handling, and workflow recovery for Temporal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import structlog
from temporalio import activity
from temporalio.common import RetryPolicy

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class WorkflowTimeouts:
    """Configurable timeouts for durable workflow activities."""

    start_to_close: timedelta = timedelta(minutes=5)
    schedule_to_close: timedelta = timedelta(minutes=15)
    heartbeat_timeout: timedelta = timedelta(seconds=30)


def get_default_retry_policy(
    max_attempts: int = 3,
    initial_interval_seconds: float = 1.0,
    backoff_coefficient: float = 2.0,
    max_interval_seconds: float = 30.0,
    non_retryable_errors: list[str] | None = None,
) -> RetryPolicy:
    """Return a standard exponential-backoff retry policy for activities."""
    return RetryPolicy(
        initial_interval=timedelta(seconds=initial_interval_seconds),
        backoff_coefficient=backoff_coefficient,
        maximum_interval=timedelta(seconds=max_interval_seconds),
        maximum_attempts=max_attempts,
        non_retryable_error_types=non_retryable_errors or ["ValueError", "TaskNotFoundError"],
    )


async def send_activity_heartbeat(step_name: str, progress: int, details: dict[str, Any] | None = None) -> None:
    """Send heartbeat from an activity to indicate liveness and progress.

    If the worker host or process crashes, Temporal uses the heartbeat_timeout
    to rapidly detect failure and reschedule the activity on a healthy worker.
    """
    heartbeat_data = {
        "step": step_name,
        "progress": progress,
        "details": details or {},
    }
    try:
        activity.heartbeat(heartbeat_data)
        logger.debug("activity_heartbeat_sent", step=step_name, progress=progress)
    except Exception as exc:
        # In mock or offline mode, activity context may not be active
        logger.debug("heartbeat_context_info", error=str(exc))
