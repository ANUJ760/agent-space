"""Task state machine and transition validation engine."""

from enum import StrEnum

from app.errors import ConflictError


class TaskStatus(StrEnum):
    """Lifecycle statuses for computational tasks."""

    TODO = "TODO"
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


# Transition mapping: Current Status -> Set of permitted next statuses
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.TODO: {
        TaskStatus.CLAIMED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.CLAIMED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.TODO,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.REVIEW,
        TaskStatus.DONE,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.TODO,
        TaskStatus.IN_PROGRESS,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REVIEW: {
        TaskStatus.DONE,
        TaskStatus.IN_PROGRESS,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PAUSED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.FAILED: {
        TaskStatus.TODO,
        TaskStatus.CANCELLED,
    },
    TaskStatus.CANCELLED: {
        TaskStatus.TODO,
    },
    TaskStatus.DONE: {
        TaskStatus.TODO,
    },
}


def validate_transition(
    current: TaskStatus | str,
    requested: TaskStatus | str,
) -> bool:
    """Validate whether transitioning from current to requested status is permitted.

    Returns True if current == requested (no-op) or if requested is in ALLOWED_TRANSITIONS.
    """
    try:
        current_status = TaskStatus(current)
        requested_status = TaskStatus(requested)
    except ValueError:
        return False

    if current_status == requested_status:
        return True

    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    return requested_status in allowed


def check_transition_or_raise(
    current: TaskStatus | str,
    requested: TaskStatus | str,
) -> None:
    """Validate state transition, raising ConflictError if forbidden."""
    if not validate_transition(current, requested):
        raise ConflictError(
            code="INVALID_STATE_TRANSITION",
            message=f"Cannot transition task from '{current}' to '{requested}'.",
            details={
                "current_status": str(current),
                "requested_status": str(requested),
            },
        )
