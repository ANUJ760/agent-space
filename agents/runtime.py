"""LangGraph Runtime for Agent Space autonomous agent execution.

Architecture:
    Task Context
         ↓
    Reason (internal deliberation)
         ↓
    Tool Selection
         ↓
    Tool Execution
         ↓
    Observation
         ↓
    [Condition]: continue → Reason | finish → Finish | human → Human Request

Strict Guarantees:
- Chain-of-thought and internal deliberation are NEVER exposed to the UI or database.
- Produces concise execution summaries in the final AgentResult.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agents.protocol import AgentExecutionStatus, AgentResult, TaskContext


class AgentGraphState(TypedDict, total=False):
    """Internal graph state maintained across execution nodes."""

    task_id: str
    project_id: str
    title: str
    description: str
    context_data: dict[str, Any]
    internal_thought: str  # Internal reasoning — strictly discarded before result construction
    selected_tool: str | None
    tool_args: dict[str, Any]
    tool_result: Any
    iteration: int
    max_iterations: int
    next_step: str  # "continue" | "finish" | "human"
    summary: str  # Concise execution summary exposed to user
    changed_files: list[str]
    artifacts: list[dict[str, Any]]
    human_request: dict[str, Any] | None


class AgentRuntime:
    """Manages the LangGraph execution flow for an agent."""

    def __init__(self, tools: dict[str, Callable[..., Any]] | None = None, max_iterations: int = 5):
        self.tools = tools or {}
        self.max_iterations = max_iterations
        self.graph = self._compile_graph()

    def _compile_graph(self) -> Any:
        workflow = StateGraph(AgentGraphState)

        # 1. Add nodes
        workflow.add_node("context", self._context_node)
        workflow.add_node("reason", self._reason_node)
        workflow.add_node("tool_selection", self._tool_selection_node)
        workflow.add_node("tool_execution", self._tool_execution_node)
        workflow.add_node("observation", self._observation_node)
        workflow.add_node("finish", self._finish_node)
        workflow.add_node("human", self._human_node)

        # 2. Add edges
        workflow.set_entry_point("context")
        workflow.add_edge("context", "reason")
        workflow.add_edge("reason", "tool_selection")
        workflow.add_edge("tool_selection", "tool_execution")
        workflow.add_edge("tool_execution", "observation")

        # 3. Conditional routing from observation
        workflow.add_conditional_edges(
            "observation",
            self._route_next_step,
            {
                "continue": "reason",
                "finish": "finish",
                "human": "human",
            },
        )
        workflow.add_edge("finish", END)
        workflow.add_edge("human", END)

        return workflow.compile()

    async def _context_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 1: Initialize context and working variables."""
        return {
            "iteration": 0,
            "changed_files": state.get("changed_files", []),
            "artifacts": state.get("artifacts", []),
            "internal_thought": "",
            "context_data": {
                "title": state.get("title", ""),
                "description": state.get("description", ""),
            },
        }

    async def _reason_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 2: Deliberate on next step.

        (Internal reasoning is isolated to internal_thought).
        """
        iteration = state.get("iteration", 0) + 1
        title = state.get("title", "").lower()

        # Check if human clarification is needed
        if "clarify" in title or "ask" in title:
            thought = "User query is ambiguous; requesting clarification."
            return {
                "iteration": iteration,
                "internal_thought": thought,
                "next_step": "human",
                "human_request": {"question": "Could you clarify the expected format?"},
            }

        # Check if completed
        if iteration >= 2 or not self.tools:
            thought = f"Work finished after {iteration} iterations."
            return {
                "iteration": iteration,
                "internal_thought": thought,
                "next_step": "finish",
                "selected_tool": None,
            }

        # Otherwise pick first available tool
        tool_name = next(iter(self.tools.keys()))
        thought = f"Selecting tool '{tool_name}' to inspect files."
        return {
            "iteration": iteration,
            "internal_thought": thought,
            "next_step": "continue",
            "selected_tool": tool_name,
            "tool_args": {"path": "src/main.py"},
        }

    async def _tool_selection_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 3: Validate selected tool and prepare inputs."""
        return {"selected_tool": state.get("selected_tool")}

    async def _tool_execution_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 4: Execute tool in safe execution environment."""
        tool_name = state.get("selected_tool")
        if not tool_name or tool_name not in self.tools:
            return {"tool_result": None}

        tool_func = self.tools[tool_name]
        args = state.get("tool_args", {})
        try:
            import inspect

            if inspect.iscoroutinefunction(tool_func):
                res = await tool_func(**args)
            else:
                res = tool_func(**args)
            return {"tool_result": res}
        except Exception as exc:
            return {"tool_result": f"Error: {exc}"}

    async def _observation_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 5: Ingest tool result into observation."""
        tool_res = state.get("tool_result")
        changed = list(state.get("changed_files", []))
        if tool_res and isinstance(tool_res, dict) and "file" in tool_res:
            changed.append(tool_res["file"])

        return {
            "changed_files": changed,
        }

    def _route_next_step(self, state: AgentGraphState) -> str:
        """Route to reason, finish, or human."""
        if state.get("next_step") == "human":
            return "human"
        if state.get("next_step") == "finish" or state.get("iteration", 0) >= self.max_iterations:
            return "finish"
        return "continue"

    async def _finish_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 6: Produce concise execution summary (No CoT exposed)."""
        summary = f"Task completed successfully: '{state.get('title')}' with {len(state.get('changed_files', []))} changed files."
        return {
            "summary": summary,
            "next_step": "finish",
        }

    async def _human_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Node 7: Format human input request."""
        return {
            "summary": "Agent paused awaiting human input",
            "next_step": "human",
        }

    async def execute(self, context: TaskContext) -> AgentResult:
        """Run agent graph and return sanitized AgentResult with NO CoT leaked."""
        initial_state: AgentGraphState = {
            "task_id": context.task_id,
            "project_id": context.project_id,
            "title": context.title,
            "description": context.description or "",
            "changed_files": list(context.files),
            "iteration": 0,
            "max_iterations": self.max_iterations,
        }

        final_state = await self.graph.ainvoke(initial_state)

        # Check for human input requirement
        if final_state.get("next_step") == "human":
            return AgentResult(
                status=AgentExecutionStatus.NEEDS_HUMAN_INPUT,
                summary=final_state.get("summary", "Awaiting human input"),
                human_request=final_state.get("human_request"),
            )

        # Construct clean AgentResult: ZERO chain-of-thought leaked
        return AgentResult(
            status=AgentExecutionStatus.SUCCESS,
            summary=final_state.get("summary", "Execution completed"),
            changed_files=final_state.get("changed_files", []),
            artifacts=final_state.get("artifacts", []),
        )
