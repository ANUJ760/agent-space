"""Tests for M34 — Agent Registry & Capabilities.

Validates:
- AgentRole and AgentCapability enum formalization
- AgentProfile capability matching
- AgentWorkload utilization and capacity logic
- AgentCapabilityRegistry registration, task assignment, and release
- Scheduler candidate matching by capability subset and workload ranking
"""

from agents.capabilities import (
    AgentAvailability,
    AgentCapability,
    AgentCapabilityRegistry,
    AgentProfile,
    AgentRole,
    AgentWorkload,
)


class TestAgentCapabilities:
    def test_capabilities_and_roles(self) -> None:
        assert AgentRole.DEVELOPER == "DEVELOPER"
        assert AgentRole.REVIEWER == "REVIEWER"
        assert AgentCapability.PYTHON == "python"
        assert AgentCapability.TYPESCRIPT == "typescript"
        assert AgentCapability.DOCKER == "docker"
        assert AgentCapability.GPU == "gpu"
        assert AgentCapability.VISION == "vision"
        assert AgentCapability.RESEARCH == "research"

    def test_agent_profile_has_capabilities(self) -> None:
        profile = AgentProfile(
            agent_id="agent-1",
            name="Fullstack Agent",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.PYTHON, AgentCapability.TYPESCRIPT, AgentCapability.GIT},
        )
        assert profile.has_capabilities([AgentCapability.PYTHON]) is True
        assert profile.has_capabilities([AgentCapability.PYTHON, AgentCapability.TYPESCRIPT]) is True
        assert profile.has_capabilities([AgentCapability.PYTHON, AgentCapability.DOCKER]) is False

    def test_workload_capacity(self) -> None:
        workload = AgentWorkload(active_tasks=1, max_concurrent_tasks=2)
        assert workload.is_at_capacity is False
        assert workload.utilization == 0.5

        workload.active_tasks = 2
        assert workload.is_at_capacity is True
        assert workload.utilization == 1.0


class TestAgentCapabilityRegistry:
    async def test_registry_matching_and_ranking(self) -> None:
        registry = AgentCapabilityRegistry()

        # Agent 1: Python + Docker, 1 active task
        p1 = AgentProfile(
            agent_id="a1",
            name="Coder 1",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.PYTHON, AgentCapability.DOCKER},
            workload=AgentWorkload(active_tasks=1, max_concurrent_tasks=2),
        )
        # Agent 2: Python + Docker, 0 active tasks (idle)
        p2 = AgentProfile(
            agent_id="a2",
            name="Coder 2",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.PYTHON, AgentCapability.DOCKER},
            workload=AgentWorkload(active_tasks=0, max_concurrent_tasks=2),
        )
        # Agent 3: Reviewer (wrong role)
        p3 = AgentProfile(
            agent_id="a3",
            name="Reviewer 1",
            role=AgentRole.REVIEWER,
            capabilities={AgentCapability.PYTHON, AgentCapability.DOCKER},
            workload=AgentWorkload(active_tasks=0, max_concurrent_tasks=2),
        )

        await registry.register(p1)
        await registry.register(p2)
        await registry.register(p3)

        # Query candidates for Developer with Python + Docker
        candidates = await registry.find_candidates(
            required_capabilities=[AgentCapability.PYTHON, AgentCapability.DOCKER],
            role=AgentRole.DEVELOPER,
        )
        assert len(candidates) == 2
        # Coder 2 should be first because utilization is 0.0 vs 0.5
        assert candidates[0].agent_id == "a2"
        assert candidates[1].agent_id == "a1"

        best = await registry.find_best_agent(
            required_capabilities=[AgentCapability.PYTHON, AgentCapability.DOCKER],
            role=AgentRole.DEVELOPER,
        )
        assert best is not None
        assert best.agent_id == "a2"

    async def test_assign_and_release_task_lifecycle(self) -> None:
        registry = AgentCapabilityRegistry()
        profile = AgentProfile(
            agent_id="agent-single",
            name="Solo Coder",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.PYTHON},
            workload=AgentWorkload(active_tasks=0, max_concurrent_tasks=1),
        )
        await registry.register(profile)

        # 1. Assign first task -> succeeds, now at capacity
        ok1 = await registry.assign_task("agent-single")
        assert ok1 is True
        p = await registry.get_profile("agent-single")
        assert p is not None
        assert p.workload.active_tasks == 1
        assert p.availability == AgentAvailability.BUSY

        # 2. Assign second task -> fails because at capacity
        ok2 = await registry.assign_task("agent-single")
        assert ok2 is False

        # 3. Release task -> active count drops, availability returns to AVAILABLE
        released = await registry.release_task("agent-single")
        assert released is True
        p = await registry.get_profile("agent-single")
        assert p is not None
        assert p.workload.active_tasks == 0
        assert p.availability == AgentAvailability.AVAILABLE
