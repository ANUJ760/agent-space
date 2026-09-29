"""Tests for M33 — Agent Protocol.

Validates:
- TaskContext construction and parameters
- AgentResult construction and serialization to dict
- BaseAgent interface compliance and subclass execution
- Diverse agent outcome results (SUCCESS, NEEDS_HUMAN_INPUT, HANDOFF)
"""

from agents.protocol import (
    AgentExecutionStatus,
    AgentResult,
    BaseAgent,
    TaskContext,
)


class MockGreetingAgent(BaseAgent):
    """Simple test agent implementing BaseAgent protocol."""

    async def execute(self, context: TaskContext) -> AgentResult:
        if "help" in context.title.lower():
            return AgentResult(
                status=AgentExecutionStatus.NEEDS_HUMAN_INPUT,
                summary="Agent requires clarification",
                human_request={"question": "Which database schema should we use?"},
            )
        if "delegate" in context.title.lower():
            return AgentResult(
                status=AgentExecutionStatus.HANDOFF,
                summary="Delegating to reviewer",
                handoff={"target_role": "REVIEWER", "reason": "Requires human sign-off"},
            )
        return AgentResult(
            status=AgentExecutionStatus.SUCCESS,
            summary=f"Completed task '{context.title}' successfully",
            changed_files=["src/main.py", "tests/test_main.py"],
            artifacts=[{"name": "diff.patch", "size_bytes": 1024}],
            tests={"passed": 12, "failed": 0, "duration_s": 1.2},
        )


class TestAgentProtocol:
    def test_task_context_defaults(self) -> None:
        ctx = TaskContext(
            task_id="t-1",
            project_id="p-1",
            title="Fix login bug",
        )
        assert ctx.task_id == "t-1"
        assert ctx.title == "Fix login bug"
        assert ctx.files == []
        assert ctx.parameters == {}
        assert ctx.history == []

    def test_agent_result_to_dict(self) -> None:
        res = AgentResult(
            status=AgentExecutionStatus.SUCCESS,
            summary="Refactored database pool",
            changed_files=["db.py"],
            artifacts=[{"id": "art-1"}],
            tests={"passed": 5},
        )
        d = res.to_dict()
        assert d["status"] == "SUCCESS"
        assert d["summary"] == "Refactored database pool"
        assert d["changed_files"] == ["db.py"]
        assert len(d["artifacts"]) == 1
        assert d["tests"] == {"passed": 5}
        assert d["handoff"] is None
        assert d["human_request"] is None

    async def test_agent_execution_success(self) -> None:
        agent = MockGreetingAgent(name="Greeter", role="DEVELOPER", capabilities=["python"])
        ctx = TaskContext(task_id="t-2", project_id="p-1", title="Build feature X")

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert "Completed task" in result.summary
        assert len(result.changed_files) == 2
        assert result.tests["passed"] == 12

    async def test_agent_execution_needs_human_input(self) -> None:
        agent = MockGreetingAgent(name="Greeter", role="DEVELOPER")
        ctx = TaskContext(task_id="t-3", project_id="p-1", title="I need help with DB")

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert result.human_request is not None
        assert "database schema" in result.human_request["question"]

    async def test_agent_execution_handoff(self) -> None:
        agent = MockGreetingAgent(name="Greeter", role="DEVELOPER")
        ctx = TaskContext(task_id="t-4", project_id="p-1", title="Delegate to reviewer")

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.HANDOFF
        assert result.handoff is not None
        assert result.handoff["target_role"] == "REVIEWER"
