"""Unit tests for M57 (Project Progress calculation and weighted states)."""

import uuid
from types import SimpleNamespace

from app.services.progress import ProjectProgressCalculator


def test_progress_with_default_weights():
    calc = ProjectProgressCalculator()
    proj_id = uuid.uuid4()

    tasks = [
        SimpleNamespace(status="TODO"),  # weight 0.0
        SimpleNamespace(status="CLAIMED"),  # weight 0.10
        SimpleNamespace(status="IN_PROGRESS"),  # weight 0.50
        SimpleNamespace(status="DONE"),  # weight 1.00
    ]

    res = calc.calculate(project_id=proj_id, tasks=tasks, agent_activity_count=12)

    # Total score = 0.0 + 0.10 + 0.50 + 1.00 = 1.60
    # Percentage = (1.60 / 4) * 100 = 40.0%
    assert res.total_progress_pct == 40.0
    assert res.total_tasks == 4
    assert res.completed_tasks == 1
    assert res.active_tasks == 2  # CLAIMED, IN_PROGRESS
    assert res.todo_tasks == 1
    assert res.blocked_tasks == 0
    assert res.agent_activity_count == 12


def test_progress_all_done():
    calc = ProjectProgressCalculator()
    proj_id = uuid.uuid4()
    tasks = [SimpleNamespace(status="DONE"), SimpleNamespace(status="DONE")]

    res = calc.calculate(project_id=proj_id, tasks=tasks)
    assert res.total_progress_pct == 100.0
    assert res.completed_tasks == 2


def test_progress_zero_tasks():
    calc = ProjectProgressCalculator()
    proj_id = uuid.uuid4()

    res = calc.calculate(project_id=proj_id, tasks=[])
    assert res.total_progress_pct == 0.0
    assert res.total_tasks == 0


def test_progress_custom_weights():
    custom = {
        "REVIEW": 0.85,
        "CLAIMED": 0.20,
    }
    calc = ProjectProgressCalculator(custom_weights=custom)
    proj_id = uuid.uuid4()

    tasks = [
        SimpleNamespace(status="CLAIMED"),  # 0.20
        SimpleNamespace(status="REVIEW"),  # 0.85
    ]
    res = calc.calculate(project_id=proj_id, tasks=tasks)
    # Total = 1.05 / 2 = 52.5%
    assert res.total_progress_pct == 52.5
    assert res.weights_applied["REVIEW"] == 0.85
    assert res.weights_applied["CLAIMED"] == 0.20
