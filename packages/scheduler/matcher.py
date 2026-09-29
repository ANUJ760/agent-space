"""Capability matching engine for task scheduler (M59).

Matches required task capabilities and resource requirements (e.g. Python, Vision, GPU)
against candidate agent capabilities and rejects incompatible candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.capabilities import AgentAvailability, AgentCapability, AgentProfile


@dataclass
class MatchResult:
    """Outcome of evaluating an agent against task requirements."""

    agent_id: str
    agent_name: str
    is_compatible: bool
    missing_capabilities: list[str] = field(default_factory=list)
    rejection_reason: str | None = None
    match_score: float = 0.0


class CapabilityMatcher:
    """Matches task requirements against agent profiles."""

    @staticmethod
    def evaluate_agent(
        agent: AgentProfile,
        required_capabilities: list[str | AgentCapability],
        requires_gpu: bool = False,
        allow_busy: bool = False,
    ) -> MatchResult:
        """Evaluate if an agent satisfies task requirements."""
        missing: list[str] = []

        agent_identifier = getattr(agent, "agent_id", getattr(agent, "id", ""))
        # 1. Availability check
        if not allow_busy and agent.availability != AgentAvailability.AVAILABLE:
            return MatchResult(
                agent_id=agent_identifier,
                agent_name=agent.name,
                is_compatible=False,
                rejection_reason=f"Agent is {agent.availability.value}, not AVAILABLE",
            )

        # 2. Capacity check
        if agent.workload.is_at_capacity:
            return MatchResult(
                agent_id=agent_identifier,
                agent_name=agent.name,
                is_compatible=False,
                rejection_reason=f"Agent workload at full capacity ({agent.workload.active_tasks}/{agent.workload.max_concurrent_tasks})",
            )

        # 3. GPU requirement
        if requires_gpu and AgentCapability.GPU not in agent.capabilities:
            missing.append(AgentCapability.GPU.value)

        # 4. Discrete capability checks
        for req in required_capabilities:
            req_str = req.value if isinstance(req, AgentCapability) else str(req).lower()
            agent_cap_strs = [c.value for c in agent.capabilities]
            if req_str not in agent_cap_strs:
                missing.append(req_str)

        if missing:
            return MatchResult(
                agent_id=agent_identifier,
                agent_name=agent.name,
                is_compatible=False,
                missing_capabilities=missing,
                rejection_reason=f"Missing required capabilities: {', '.join(missing)}",
            )

        # Calculate score (lower workload = higher score)
        score = 100.0 - (agent.workload.utilization * 50.0)

        return MatchResult(
            agent_id=agent_identifier,
            agent_name=agent.name,
            is_compatible=True,
            match_score=score,
        )
