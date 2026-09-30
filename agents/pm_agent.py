"""Project Manager Agent for Agent Space.

Decomposes high-level human goals into structured work breakdown structures (WBS),
milestones, task DAGs, and dependencies for autonomous agent teams.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import structlog

from agents.capabilities import AgentCapability, AgentRole
from agents.protocol import AgentExecutionStatus, AgentResult, BaseAgent, TaskContext

logger = structlog.stdlib.get_logger(__name__)


class ProjectManagerAgent(BaseAgent):
    """Specialized Project Manager agent orchestrating initiative decomposition and scheduling."""

    def __init__(
        self,
        name: str = "ProjectManagerAgent",
        model: str = "llama3.1:8b",
        tools: dict[str, Callable[..., Any]] | None = None,
        allowed_tools: set[str] | None = None,
    ):
        super().__init__(
            name=name,
            role=AgentRole.COORDINATOR,
            capabilities=[AgentCapability.RESEARCH, AgentCapability.GIT],
            model=model,
        )
        self.tools = tools or {}
        self.allowed_tools = allowed_tools

    async def execute(self, context: TaskContext) -> AgentResult:
        """Decompose project objective into structured execution phases and task DAG."""
        logger.info("pm_agent_started", task_id=context.task_id, title=context.title)

        goal = context.description or context.title

        # Check for human clarification requirement
        if context.parameters.get("require_human_input") or "clarify" in goal.lower():
            return AgentResult(
                status=AgentExecutionStatus.NEEDS_HUMAN_INPUT,
                summary=f"Project scope clarification required for '{goal}'",
                human_request={
                    "prompt": f"Clarify project requirements for: {goal}",
                    "task_id": context.task_id,
                },
            )

        try:
            # Step 1: Decompose objective into ordered lifecycle phases
            phases = [
                {
                    "step": 1,
                    "phase": "Research",
                    "role": "RESEARCHER",
                    "title": f"Research technical approaches for {goal}",
                    "description": "Analyze technical stack, algorithms, libraries, and prior art.",
                    "depends_on": [],
                },
                {
                    "step": 2,
                    "phase": "Architecture",
                    "role": "ARCHITECT",
                    "title": f"Architect system design for {goal}",
                    "description": "Define database schemas, API specs, component boundaries, and security rules.",
                    "depends_on": ["Research"],
                },
                {
                    "step": 3,
                    "phase": "Coding",
                    "role": "DEVELOPER",
                    "title": f"Implement core functionality for {goal}",
                    "description": "Develop models, services, endpoints, and data storage.",
                    "depends_on": ["Architecture"],
                },
                {
                    "step": 4,
                    "phase": "Testing",
                    "role": "TESTER",
                    "title": f"Comprehensive test suite for {goal}",
                    "description": "Validate functional correctness, edge cases, performance, and security.",
                    "depends_on": ["Coding"],
                },
                {
                    "step": 5,
                    "phase": "Review",
                    "role": "REVIEWER",
                    "title": f"Multi-pillar quality review for {goal}",
                    "description": "Evaluate code quality, security posture, and requirements satisfaction.",
                    "depends_on": ["Testing"],
                },
                {
                    "step": 6,
                    "phase": "Human Approval",
                    "role": "HUMAN",
                    "title": f"Human deployment approval for {goal}",
                    "description": "Present artifacts to human operator for deployment sign-off.",
                    "depends_on": ["Review"],
                },
            ]

            # Step 2: Invoke planning / task creation tools if configured
            if "create_tasks" in self.tools:
                await self._call_tool("create_tasks", phases=phases)

            plan_markdown = f"# Project Plan: {goal}\n\n"
            plan_markdown += f"**Goal**: {goal}\n\n"
            plan_markdown += "## Planned Work Breakdown Structure\n\n"
            for p in phases:
                plan_markdown += (
                    f"- **Step {p['step']} ({p['phase']})**: {p['title']} [{p['role']}]\n"
                )

            artifacts = [
                {
                    "name": "project_plan.md",
                    "type": "markdown",
                    "content": plan_markdown,
                },
                {
                    "name": "work_breakdown.json",
                    "type": "json",
                    "content": phases,
                },
            ]

            summary = (
                f"Project Manager planned '{goal}' across {len(phases)} lifecycle phases. "
                "Handoff initiated to Research."
            )

            return AgentResult(
                status=AgentExecutionStatus.SUCCESS,
                summary=summary,
                artifacts=artifacts,
                handoff={
                    "next_phase": "Research",
                    "next_role": "RESEARCHER",
                    "phases": phases,
                },
            )

        except Exception as exc:
            logger.error("pm_agent_failed", error=str(exc))
            return AgentResult(
                status=AgentExecutionStatus.FAILED,
                summary=f"Project planning failed: {exc}",
            )

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            raise PermissionError(f"Tool '{tool_name}' not permitted for agent '{self.name}'")
        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return {}
        if inspect.iscoroutinefunction(tool_func):
            return await tool_func(**kwargs)
        return tool_func(**kwargs)
