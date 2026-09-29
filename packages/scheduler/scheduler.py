"""Scheduler engine for AgentSpace (M58).

Coordinates:
- Prerequisite dependency checks (rejects incomplete dependencies).
- Capability matching (M59).
- Workload-aware candidate selection.
- Decision explainability logging (M61).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.capabilities import AgentProfile
from packages.scheduler.explainability import (
    CandidateEvaluationRecord,
    SchedulingDecision,
)
from packages.scheduler.matcher import CapabilityMatcher


@dataclass
class ScheduleTaskRequest:
    """Input parameters for a scheduling request."""

    task_id: str
    project_id: str
    prerequisite_task_ids: list[str]
    priority: str = "MEDIUM"
    required_capabilities: list[str] = None
    requires_gpu: bool = False
    preferred_model: str | None = None
    metadata: dict[str, Any] = None


@dataclass
class ScheduleResult:
    """Outcome of scheduling a task."""

    scheduled: bool
    selected_agent: AgentProfile | None = None
    alternatives: list[AgentProfile] = None
    reason: str = ""
    decision: SchedulingDecision | None = None


class TaskScheduler:
    """Scheduler engine that matches tasks to best available agents."""

    def __init__(self, matcher: CapabilityMatcher | None = None) -> None:
        self.matcher = matcher or CapabilityMatcher()

    def schedule(
        self,
        request: ScheduleTaskRequest,
        completed_task_ids: set[str],
        candidate_agents: list[AgentProfile],
    ) -> ScheduleResult:
        """Schedule task to the optimal agent satisfying dependencies and capabilities."""
        req_caps = request.required_capabilities or []
        decision = SchedulingDecision(
            task_id=request.task_id,
            project_id=request.project_id,
            required_capabilities=req_caps,
            requires_gpu=request.requires_gpu,
        )

        # 1. Dependency Validation Rule: "Do not schedule incomplete dependencies."
        missing_prereqs = [p for p in request.prerequisite_task_ids if p not in completed_task_ids]
        if missing_prereqs:
            reason = f"Cannot schedule: prerequisite dependencies not completed ({', '.join(missing_prereqs)})"
            decision.selection_reason = reason
            return ScheduleResult(
                scheduled=False,
                selected_agent=None,
                alternatives=[],
                reason=reason,
                decision=decision,
            )

        # 2. Evaluate all candidate agents
        compatible_candidates: list[tuple[AgentProfile, float]] = []

        for agent in candidate_agents:
            aid = getattr(agent, "agent_id", getattr(agent, "id", ""))
            match = self.matcher.evaluate_agent(
                agent=agent,
                required_capabilities=req_caps,
                requires_gpu=request.requires_gpu,
            )
            eval_record = CandidateEvaluationRecord(
                agent_id=aid,
                agent_name=agent.name,
                is_compatible=match.is_compatible,
                rejection_reason=match.rejection_reason,
                missing_capabilities=match.missing_capabilities,
                workload=agent.workload.active_tasks,
                score=match.match_score,
            )
            decision.candidates.append(eval_record)

            if match.is_compatible:
                compatible_candidates.append((agent, match.match_score))

        # 3. No compatible agents found
        if not compatible_candidates:
            reason = f"No available agent satisfies required capabilities: {req_caps}"
            decision.selection_reason = reason
            return ScheduleResult(
                scheduled=False,
                selected_agent=None,
                alternatives=[],
                reason=reason,
                decision=decision,
            )

        # 4. Sort compatible candidates by score (highest score / lowest workload first)
        compatible_candidates.sort(key=lambda pair: pair[1], reverse=True)
        winner_agent, winner_score = compatible_candidates[0]
        alt_agents = [pair[0] for pair in compatible_candidates[1:]]

        winner_id = getattr(winner_agent, "agent_id", getattr(winner_agent, "id", ""))
        reason = (
            f"Selected '{winner_agent.name}' (workload: {winner_agent.workload.active_tasks}/"
            f"{winner_agent.workload.max_concurrent_tasks}, score: {winner_score})"
        )
        decision.selected_agent_id = winner_id
        decision.selected_agent_name = winner_agent.name
        decision.selection_reason = reason
        decision.alternatives = [getattr(a, "agent_id", getattr(a, "id", "")) for a in alt_agents]

        return ScheduleResult(
            scheduled=True,
            selected_agent=winner_agent,
            alternatives=alt_agents,
            reason=reason,
            decision=decision,
        )
