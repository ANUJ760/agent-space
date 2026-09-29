"""Scheduling explainability and auditable decision logging (M61).

Records candidate agents, rejected candidates with reasons, required capabilities,
selected agent, and reproducible selection rationale.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class CandidateEvaluationRecord:
    """Evaluation record of a single agent candidate considered during scheduling."""

    agent_id: str
    agent_name: str
    is_compatible: bool
    rejection_reason: str | None = None
    missing_capabilities: list[str] = field(default_factory=list)
    workload: int = 0
    score: float = 0.0


@dataclass
class SchedulingDecision:
    """Complete, reproducible audit record of a scheduler assignment decision."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    project_id: str = ""
    selected_agent_id: str | None = None
    selected_agent_name: str | None = None
    selection_reason: str = ""
    alternatives: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    requires_gpu: bool = False
    candidates: list[CandidateEvaluationRecord] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_reproducible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for audit logs or database storage."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "selected_agent_id": self.selected_agent_id,
            "selected_agent_name": self.selected_agent_name,
            "selection_reason": self.selection_reason,
            "alternatives": self.alternatives,
            "required_capabilities": self.required_capabilities,
            "requires_gpu": self.requires_gpu,
            "candidate_count": len(self.candidates),
            "candidates": [
                {
                    "agent_id": c.agent_id,
                    "agent_name": c.agent_name,
                    "is_compatible": c.is_compatible,
                    "rejection_reason": c.rejection_reason,
                    "workload": c.workload,
                    "score": c.score,
                }
                for c in self.candidates
            ],
            "timestamp": self.timestamp.isoformat(),
        }
