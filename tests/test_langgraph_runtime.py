"""Tests for M36 — LangGraph Runtime.

Validates:
- Graph compilation and execution lifecycle
- Tool selection, execution, and observation ingestion
- Zero exposure of internal chain-of-thought in AgentResult
- Concise execution summary generation
- Conditional branch to human input request
"""

from agents.protocol import AgentExecutionStatus, TaskContext
from agents.runtime import AgentRuntime


class TestLangGraphRuntime:
    async def test_execution_without_tools(self) -> None:
        runtime = AgentRuntime()
        ctx = TaskContext(
            task_id="t-1",
            project_id="p-1",
            title="Update database index",
        )

        result = await runtime.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert "Update database index" in result.summary

        # Verify strict zero CoT leakage
        d = result.to_dict()
        assert "internal_thought" not in d
        assert "thought" not in d
        assert "deliberation" not in d

    async def test_execution_with_tool_invocation(self) -> None:
        async def mock_edit_file(path: str) -> dict[str, str]:
            return {"file": path, "status": "modified"}

        runtime = AgentRuntime(tools={"edit_file": mock_edit_file})
        ctx = TaskContext(
            task_id="t-2",
            project_id="p-1",
            title="Refactor controller",
        )

        result = await runtime.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert "src/main.py" in result.changed_files
        assert "Refactor controller" in result.summary

    async def test_conditional_routing_to_human_input(self) -> None:
        runtime = AgentRuntime()
        ctx = TaskContext(
            task_id="t-3",
            project_id="p-1",
            title="Ask user for clarification on API contract",
        )

        result = await runtime.execute(ctx)
        assert result.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert result.human_request is not None
        assert "clarify" in result.human_request["question"].lower()
