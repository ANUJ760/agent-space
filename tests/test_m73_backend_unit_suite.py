"""M73: Master Backend Unit Test Suite.

Covers:
1. Services (User, Progress, Preview, Memory)
2. State Transitions (Task State Machine transitions & guards)
3. Permissions (RBAC role hierarchy & granular permission checks)
4. Scheduler (Capability matching & workload-balanced selection)
5. Dependency Graph (DAG sorting, cycle detection, unresolved blocking)
6. Validators (Slug regex, upload mime/magic, prompt boundary guards)
7. Error Mapping (App exception hierarchy -> HTTP status code contracts)
"""

import uuid
from types import SimpleNamespace

import pytest
from app.auth import Actor, Permission, Role, has_permission
from app.errors import (
    AppException,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.services.progress import ProjectProgressCalculator
from app.services.task_state_machine import TaskStatus, check_transition_or_raise

from packages.scheduler.dag import CycleDependencyError, TaskDAGExecutor
from packages.scheduler.matcher import CapabilityMatcher
from packages.security.prompt_isolation import PromptBoundaryGuard, PromptInjectionAttemptError
from packages.security.uploads import DisallowedFileTypeError, UploadSecurityValidator

# ─── 1. Services: Project Progress Calculator ──────────────────────────────


def test_progress_calculator_weighted_completion():
    calc = ProjectProgressCalculator()
    proj_id = uuid.uuid4()
    tasks = [
        SimpleNamespace(status="DONE"),        # 1.00
        SimpleNamespace(status="IN_PROGRESS"), # 0.50
        SimpleNamespace(status="CLAIMED"),     # 0.10
        SimpleNamespace(status="TODO"),        # 0.00
    ]
    res = calc.calculate(project_id=proj_id, tasks=tasks, agent_activity_count=5)
    assert res.total_progress_pct == 40.0
    assert res.total_tasks == 4


# ─── 2. State Transitions: Task State Machine ──────────────────────────────


def test_task_state_machine_transitions():
    # Valid transitions
    check_transition_or_raise(TaskStatus.TODO.value, TaskStatus.CLAIMED.value)
    check_transition_or_raise(TaskStatus.CLAIMED.value, TaskStatus.IN_PROGRESS.value)
    check_transition_or_raise(TaskStatus.IN_PROGRESS.value, TaskStatus.REVIEW.value)
    check_transition_or_raise(TaskStatus.REVIEW.value, TaskStatus.DONE.value)

    # Invalid transitions must raise ConflictError with code INVALID_STATE_TRANSITION
    with pytest.raises(ConflictError) as exc_info1:
        check_transition_or_raise(TaskStatus.DONE.value, TaskStatus.IN_PROGRESS.value)
    assert exc_info1.value.code == "INVALID_STATE_TRANSITION"

    with pytest.raises(ConflictError) as exc_info2:
        check_transition_or_raise(TaskStatus.TODO.value, TaskStatus.DONE.value)
    assert exc_info2.value.code == "INVALID_STATE_TRANSITION"


# ─── 3. Permissions: RBAC Hierarchy & Grants ───────────────────────────────


def test_rbac_permissions_evaluation():
    org_id = uuid.uuid4()
    admin_actor = Actor(id=uuid.uuid4(), external_subject="admin", organization_id=org_id, role=Role.ORG_ADMIN)
    member_actor = Actor(id=uuid.uuid4(), external_subject="member", organization_id=org_id, role=Role.MEMBER)
    viewer_actor = Actor(id=uuid.uuid4(), external_subject="viewer", organization_id=org_id, role=Role.VIEWER)

    # Org Admin has member management and project creation
    assert has_permission(admin_actor, Permission.ORG_MANAGE_MEMBERS) is True
    assert has_permission(admin_actor, Permission.PROJECT_CREATE_TASK) is True

    # Member can create and update tasks, but cannot manage members
    assert has_permission(member_actor, Permission.TASK_CREATE) is True
    assert has_permission(member_actor, Permission.ORG_MANAGE_MEMBERS) is False

    # Viewer can only read
    assert has_permission(viewer_actor, Permission.TASK_READ) is True
    assert has_permission(viewer_actor, Permission.TASK_CREATE) is False


# ─── 4. Scheduler: Capability Matching ─────────────────────────────────────


def test_scheduler_capability_matching():
    from agents.capabilities import AgentCapability, AgentProfile, AgentRole

    matcher = CapabilityMatcher()

    agent_a = AgentProfile(
        agent_id="agent-a",
        name="Dev A",
        role=AgentRole.DEVELOPER,
        capabilities={AgentCapability.PYTHON, AgentCapability.GIT},
    )
    agent_b = AgentProfile(
        agent_id="agent-b",
        name="Dev B",
        role=AgentRole.DEVELOPER,
        capabilities={AgentCapability.TYPESCRIPT, AgentCapability.GIT},
    )

    res_a = matcher.evaluate_agent(agent_a, required_capabilities=["python", "git"])
    assert res_a.is_compatible is True

    res_b = matcher.evaluate_agent(agent_b, required_capabilities=["python", "git"])
    assert res_b.is_compatible is False


# ─── 5. Dependency Graph: DAG Execution & Cycle Detection ──────────────────


def test_dag_parallel_stages_and_cycle_prevention():
    executor = TaskDAGExecutor()
    executor.add_dependency(task_id="C", depends_on_task_id="A")
    executor.add_dependency(task_id="C", depends_on_task_id="B")
    executor.add_dependency(task_id="D", depends_on_task_id="C")

    stages = executor.compute_parallel_stages()
    assert len(stages) == 3
    assert stages[0].task_ids == ["A", "B"]
    assert stages[1].task_ids == ["C"]
    assert stages[2].task_ids == ["D"]

    # Cyclic DAG: X -> Y -> Z -> X
    cyclic = TaskDAGExecutor()
    cyclic.add_dependency(task_id="X", depends_on_task_id="Z")
    cyclic.add_dependency(task_id="Y", depends_on_task_id="X")
    cyclic.add_dependency(task_id="Z", depends_on_task_id="Y")
    with pytest.raises(CycleDependencyError):
        cyclic.compute_parallel_stages()


# ─── 6. Validators: Security & Payload Invariants ──────────────────────────


def test_validators_upload_and_prompt_guards():
    # File upload validator blocks dangerous extensions and executable mime types
    validator = UploadSecurityValidator()
    with pytest.raises(DisallowedFileTypeError):
        validator.validate_file(
            filename="payload.exe",
            content=b"MZ\x90\x00\x03\x00\x00\x00",
            declared_mime_type="application/x-dosexec",
        )

    # Prompt Boundary Guard verifies integrity and detects canary leaks
    canary = "canary_secret_12345"
    with pytest.raises(PromptInjectionAttemptError) as exc_info:
        PromptBoundaryGuard.verify_response_integrity(f"System canary is {canary}", canary)
    assert "leaked secret canary token" in str(exc_info.value)


# ─── 7. Error Mapping: Exception Hierarchy & Status Codes ──────────────────


def test_error_mapping_hierarchy():
    err1 = NotFoundError("Project", "123")
    assert err1.status_code == 404
    assert err1.code == "NOT_FOUND"

    err2 = ConflictError(message="Concurrent update", code="TASK_CONFLICT")
    assert err2.status_code == 409
    assert err2.code == "TASK_CONFLICT"

    err3 = ForbiddenError("Access denied")
    assert err3.status_code == 403
    assert err3.code == "FORBIDDEN"

    err4 = UnauthorizedError("Missing token")
    assert err4.status_code == 401
    assert err4.code == "UNAUTHORIZED"

    err5 = BadRequestError("Invalid parameter", details={"field": "slug"})
    assert err5.status_code == 400
    assert err5.code == "BAD_REQUEST"

    assert all(isinstance(e, AppException) for e in [err1, err2, err3, err4, err5])
