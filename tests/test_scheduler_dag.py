"""Unit tests for M58, M59, M60, and M61: Scheduler, Matching, DAG execution, and Explainability."""

import pytest

from agents.capabilities import (
    AgentAvailability,
    AgentCapability,
    AgentProfile,
    AgentRole,
    AgentWorkload,
)
from packages.scheduler.dag import (
    CycleDependencyError,
    TaskDAGExecutor,
)
from packages.scheduler.matcher import CapabilityMatcher
from packages.scheduler.scheduler import (
    ScheduleTaskRequest,
    TaskScheduler,
)


@pytest.fixture
def sample_agents() -> list[AgentProfile]:
    return [
        AgentProfile(
            agent_id="agent-python",
            name="Python Dev",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.PYTHON, AgentCapability.GIT},
            availability=AgentAvailability.AVAILABLE,
            workload=AgentWorkload(active_tasks=1, max_concurrent_tasks=3),
        ),
        AgentProfile(
            agent_id="agent-vision",
            name="Vision Specialist",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.VISION, AgentCapability.PYTHON},
            availability=AgentAvailability.AVAILABLE,
            workload=AgentWorkload(active_tasks=0, max_concurrent_tasks=2),
        ),
        AgentProfile(
            agent_id="agent-gpu",
            name="GPU Deep Learning",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.PYTHON, AgentCapability.GPU},
            availability=AgentAvailability.AVAILABLE,
            workload=AgentWorkload(active_tasks=0, max_concurrent_tasks=1),
        ),
        AgentProfile(
            agent_id="agent-busy",
            name="Busy Tester",
            role=AgentRole.TESTER,
            capabilities={AgentCapability.PYTHON},
            availability=AgentAvailability.BUSY,
            workload=AgentWorkload(active_tasks=3, max_concurrent_tasks=3),
        ),
    ]


def test_m59_capability_matching(sample_agents):
    matcher = CapabilityMatcher()

    # Python task -> python agent matches
    res_py = matcher.evaluate_agent(sample_agents[0], required_capabilities=["python"])
    assert res_py.is_compatible is True

    # Vision task -> python agent rejected, vision agent matches
    res_v1 = matcher.evaluate_agent(sample_agents[0], required_capabilities=["vision"])
    assert res_v1.is_compatible is False
    assert "vision" in res_v1.missing_capabilities

    res_v2 = matcher.evaluate_agent(sample_agents[1], required_capabilities=["vision"])
    assert res_v2.is_compatible is True

    # GPU task -> gpu agent matches, vision agent rejected
    res_gpu1 = matcher.evaluate_agent(
        sample_agents[1], required_capabilities=["python"], requires_gpu=True
    )
    assert res_gpu1.is_compatible is False
    assert "gpu" in res_gpu1.missing_capabilities

    res_gpu2 = matcher.evaluate_agent(
        sample_agents[2], required_capabilities=["python"], requires_gpu=True
    )
    assert res_gpu2.is_compatible is True

    # Busy agent rejected
    res_busy = matcher.evaluate_agent(sample_agents[3], required_capabilities=["python"])
    assert res_busy.is_compatible is False
    assert "BUSY" in res_busy.rejection_reason


def test_m60_dag_execution_and_parallel_stages():
    """Validates:
    A ─┐
       ├→ C → D
    B ─┘
    A and B execute concurrently. C waits for both. D waits for C.
    """
    dag = TaskDAGExecutor()
    dag.add_dependency(task_id="C", depends_on_task_id="A")
    dag.add_dependency(task_id="C", depends_on_task_id="B")
    dag.add_dependency(task_id="D", depends_on_task_id="C")

    # 1. Parallel stages
    stages = dag.compute_parallel_stages()
    assert len(stages) == 3
    assert stages[0].task_ids == ["A", "B"]  # Stage 0: concurrent A and B
    assert stages[1].task_ids == ["C"]  # Stage 1: C
    assert stages[2].task_ids == ["D"]  # Stage 2: D

    # 2. Ready tasks determination
    # Initially: only A and B ready
    assert dag.get_ready_tasks(completed_task_ids=set()) == ["A", "B"]

    # When only A completed: B still ready, C not ready
    assert dag.get_ready_tasks(completed_task_ids={"A"}) == ["B"]

    # When A and B completed: C becomes ready
    assert dag.get_ready_tasks(completed_task_ids={"A", "B"}) == ["C"]

    # When C completed: D becomes ready
    assert dag.get_ready_tasks(completed_task_ids={"A", "B", "C"}) == ["D"]


def test_m60_dag_cycle_prevention():
    dag = TaskDAGExecutor()
    dag.add_dependency(task_id="B", depends_on_task_id="A")
    dag.add_dependency(task_id="C", depends_on_task_id="B")
    dag.add_dependency(task_id="A", depends_on_task_id="C")  # Cycle A -> B -> C -> A

    with pytest.raises(CycleDependencyError) as exc_info:
        dag.validate_acyclic()
    assert "Cyclic dependency" in str(exc_info.value)


def test_m58_and_m61_scheduler_and_explainability(sample_agents):
    scheduler = TaskScheduler()

    # Case 1: Incomplete dependencies -> MUST NOT schedule
    req_blocked = ScheduleTaskRequest(
        task_id="task-child",
        project_id="proj-1",
        prerequisite_task_ids=["task-parent-1", "task-parent-2"],
        required_capabilities=["python"],
    )
    result_blocked = scheduler.schedule(
        request=req_blocked,
        completed_task_ids={"task-parent-1"},  # missing parent-2
        candidate_agents=sample_agents,
    )
    assert result_blocked.scheduled is False
    assert "prerequisite dependencies not completed" in result_blocked.reason
    assert "task-parent-2" in result_blocked.reason

    # Case 2: Dependencies satisfied -> schedules optimal agent with full explainability
    req_ready = ScheduleTaskRequest(
        task_id="task-child",
        project_id="proj-1",
        prerequisite_task_ids=["task-parent-1", "task-parent-2"],
        required_capabilities=["python"],
    )
    result = scheduler.schedule(
        request=req_ready,
        completed_task_ids={"task-parent-1", "task-parent-2"},
        candidate_agents=sample_agents,
    )
    assert result.scheduled is True
    # Vision agent and GPU agent have workload 0 (score 100), while Python dev has workload 1 (score 83.3)
    assert result.selected_agent is not None
    assert result.selected_agent.agent_id in ("agent-vision", "agent-gpu")

    # M61 Explainability verification
    dec = result.decision
    assert dec is not None
    assert dec.task_id == "task-child"
    assert len(dec.candidates) == len(sample_agents)

    # Check that rejected candidate has recorded reason
    busy_eval = next(c for c in dec.candidates if c.agent_id == "agent-busy")
    assert busy_eval.is_compatible is False
    assert "BUSY" in busy_eval.rejection_reason

    # Export to dict
    serialized = dec.to_dict()
    assert serialized["task_id"] == "task-child"
    assert serialized["selected_agent_id"] == result.selected_agent.agent_id
    assert serialized["candidate_count"] == 4
