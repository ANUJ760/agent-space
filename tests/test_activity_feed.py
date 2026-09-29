"""Unit tests for M56 (Agent Activity Feed & CoT filtering)."""

import uuid
from datetime import UTC, datetime

from app.models.outbox import OutboxEvent
from app.services.activity_feed import ActivityFeedService


def test_activity_feed_safe_summaries():
    # 1. Reading file
    evt_read = OutboxEvent(
        id=uuid.uuid4(),
        event_type="tool.read_file",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        payload={"file": "src/auth.py", "agent_name": "Coding Agent", "agent_role": "DEVELOPER"},
        created_at=datetime.now(UTC),
    )
    item_read = ActivityFeedService.format_event(evt_read)
    assert item_read.summary == "Reading src/auth.py"
    assert item_read.action == "READ_FILE"

    # 2. Running tests
    evt_test = OutboxEvent(
        id=uuid.uuid4(),
        event_type="tool.run_tests",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        payload={"agent_name": "Coding Agent", "agent_role": "DEVELOPER"},
        created_at=datetime.now(UTC),
    )
    item_test = ActivityFeedService.format_event(evt_test)
    assert item_test.summary == "Running test suite"
    assert item_test.action == "RUN_TESTS"

    # 3. Created commit
    evt_commit = OutboxEvent(
        id=uuid.uuid4(),
        event_type="tool.git_commit",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        payload={"commit_sha": "abc12345678", "agent_name": "Coding Agent", "agent_role": "DEVELOPER"},
        created_at=datetime.now(UTC),
    )
    item_commit = ActivityFeedService.format_event(evt_commit)
    assert item_commit.summary == "Created commit abc1234"
    assert item_commit.action == "GIT_COMMIT"

    # 4. Reviewer findings
    evt_review = OutboxEvent(
        id=uuid.uuid4(),
        event_type="reviewer.findings",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        payload={"issue_count": 2, "agent_name": "Reviewer Agent", "agent_role": "REVIEWER"},
        created_at=datetime.now(UTC),
    )
    item_review = ActivityFeedService.format_event(evt_review)
    assert item_review.summary == "Found 2 issues"
    assert item_review.action == "REVIEW"


def test_chain_of_thought_strictly_filtered():
    evt_cot = OutboxEvent(
        id=uuid.uuid4(),
        event_type="tool.read_file",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        payload={
            "file": "src/auth.py",
            "thought": "I should first examine lines 20-30 to see how tokens are decoded.",
            "chain_of_thought": "Step 1: Check imports. Step 2: Look for vulnerability.",
            "internal_reasoning": "This function is vulnerable to null bytes.",
            "rationale": "High risk logic.",
            "safe_detail": "file_size: 1024",
        },
        created_at=datetime.now(UTC),
    )

    clean_item = ActivityFeedService.format_event(evt_cot)

    # Safe summary must NOT contain any hidden thoughts
    assert "examine lines" not in clean_item.summary
    assert "Step 1" not in clean_item.summary

    # Metadata must NOT contain any disallowed internal keys
    meta = clean_item.metadata
    assert "thought" not in meta
    assert "chain_of_thought" not in meta
    assert "internal_reasoning" not in meta
    assert "rationale" not in meta
    assert meta["safe_detail"] == "file_size: 1024"
