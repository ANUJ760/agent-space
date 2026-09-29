"""Agent Protocol defining common agent abstractions, context, and result structures.

Establishes the uniform interface for all autonomous AI agents:
- TaskContext: Input context provided to agents during execution
- AgentResult: Structured output produced by agents
- BaseAgent: Core protocol defining the `execute(context: TaskContext) -> AgentResult` contract
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentExecutionStatus(StrEnum):
    """Execution status returned by an agent upon completion or interruption."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NEEDS_HUMAN_INPUT = "NEEDS_HUMAN_INPUT"
    HANDOFF = "HANDOFF"


@dataclass
class TaskContext:
    """Input context and parameters provided to an agent for task execution."""

    task_id: str
    project_id: str
    title: str
    description: str | None = None
    files: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Structured result returned by an agent upon executing a task."""

    status: AgentExecutionStatus = AgentExecutionStatus.SUCCESS
    summary: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    tests: dict[str, Any] = field(default_factory=dict)
    handoff: dict[str, Any] | None = None
    human_request: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "status": self.status.value if isinstance(self.status, AgentExecutionStatus) else str(self.status),
            "summary": self.summary,
            "artifacts": self.artifacts,
            "changed_files": self.changed_files,
            "tests": self.tests,
            "handoff": self.handoff,
            "human_request": self.human_request,
        }


class BaseAgent(ABC):
    """Abstract base class establishing the standard agent execution protocol."""

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: list[str] | None = None,
        model: str = "llama3.1:8b",
    ):
        self.name = name
        self.role = role
        self.capabilities = capabilities or []
        self.model = model

    @abstractmethod
    async def execute(self, context: TaskContext) -> AgentResult:
        """Execute task within the provided context and return structured AgentResult."""
        raise NotImplementedError
