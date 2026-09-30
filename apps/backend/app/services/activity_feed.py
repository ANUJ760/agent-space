"""Agent Activity Feed service.

Translates internal runtime actions and domain events into safe, human-readable
summaries while strictly eliminating any chain-of-thought or internal reasoning.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.outbox import OutboxEvent
from app.schemas.activity_feed import ActivityFeedItem

# Disallowed internal fields that must never appear in safe summaries
INTERNAL_FIELDS = {
    "thought",
    "thinking",
    "chain_of_thought",
    "internal_reasoning",
    "rationale",
    "plan_scratchpad",
}


class ActivityFeedService:
    """Formats safe agent activity events."""

    @staticmethod
    def sanitize_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        """Strip internal reasoning and chain-of-thought fields."""
        sanitized = {}
        for k, v in payload.items():
            if k.lower() in INTERNAL_FIELDS:
                continue
            if isinstance(v, dict):
                sanitized[k] = ActivityFeedService.sanitize_metadata(v)
            else:
                sanitized[k] = v
        return sanitized

    @staticmethod
    def format_event(
        event: OutboxEvent, agent_name: str = "Agent", agent_role: str = "WORKER"
    ) -> ActivityFeedItem:
        """Create a safe ActivityFeedItem from an outbox or domain event."""
        payload = dict(event.payload or {})
        clean_meta = ActivityFeedService.sanitize_metadata(payload)

        event_type = event.event_type
        action = event_type
        summary = f"{agent_name} performed {event_type}"

        # Action-specific safe summaries
        if event_type == "tool.read_file":
            filepath = payload.get("file") or payload.get("path") or "source file"
            action = "READ_FILE"
            summary = f"Reading {filepath}"

        elif event_type == "tool.run_tests":
            action = "RUN_TESTS"
            summary = "Running test suite"

        elif event_type == "tool.git_commit":
            sha = payload.get("commit_sha", "new commit")[:7]
            action = "GIT_COMMIT"
            summary = f"Created commit {sha}"

        elif event_type == "reviewer.findings":
            count = payload.get("issue_count", 0)
            action = "REVIEW"
            summary = f"Found {count} issues"

        elif event_type == "task.assigned":
            action = "CLAIMED_TASK"
            summary = f"Claimed task {payload.get('task_id', '')[:8]}"

        elif event_type == "task.takeover":
            action = "TAKEOVER"
            summary = "Human took over task"

        elif event_type == "human.input_required":
            action = "HUMAN_INPUT"
            summary = f"Requested {payload.get('request_type', 'INPUT')}: {payload.get('prompt', '')[:60]}"

        return ActivityFeedItem(
            id=event.id or uuid.uuid4(),
            project_id=event.project_id or uuid.uuid4(),
            task_id=uuid.UUID(payload["task_id"]) if payload.get("task_id") else None,
            agent_id=uuid.UUID(payload["agent_id"]) if payload.get("agent_id") else None,
            agent_name=payload.get("agent_name", agent_name),
            agent_role=payload.get("agent_role", agent_role),
            action=action,
            summary=summary,
            timestamp=event.created_at or datetime.now(UTC),
            metadata=clean_meta,
        )
