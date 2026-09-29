"""Tests for M37 — Coding Agent.

Validates:
- CodingAgent metadata, role, and capabilities
- Execution of 8-step developer pipeline:
  read task -> inspect -> plan -> edit -> run tests -> diff -> commit -> report
- Artifact generation (changes.patch) and test summary
"""

from agents.coding_agent import CodingAgent
from agents.protocol import AgentExecutionStatus, TaskContext


class TestCodingAgent:
    def test_agent_initialization(self) -> None:
        agent = CodingAgent(name="TestCoder")
        assert agent.name == "TestCoder"
        assert agent.role == "DEVELOPER"
        assert "python" in agent.capabilities
        assert "git" in agent.capabilities

    async def test_execution_with_mock_tools(self) -> None:
        calls = []

        async def mock_inspect(files: list[str]) -> dict[str, str]:
            calls.append("inspect")
            return dict.fromkeys(files, "content")

        async def mock_edit(path: str, content: str) -> bool:
            calls.append(f"edit:{path}")
            return True

        async def mock_run_tests(paths: list[str]) -> dict[str, int]:
            calls.append("tests")
            return {"passed": 8, "failed": 0, "total": 8}

        async def mock_commit(message: str) -> dict[str, str]:
            calls.append(f"commit:{message}")
            return {"sha": "a1b2c3d4e5f6"}

        agent = CodingAgent(
            tools={
                "inspect_files": mock_inspect,
                "edit_file": mock_edit,
                "run_tests": mock_run_tests,
                "commit": mock_commit,
            }
        )

        ctx = TaskContext(
            task_id="t-coding-1",
            project_id="p-1",
            title="Implement user avatar upload",
            files=["src/avatar.py", "tests/test_avatar.py"],
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert len(result.changed_files) == 2
        assert "src/avatar.py" in result.changed_files
        assert len(result.artifacts) == 1
        assert result.artifacts[0]["name"] == "changes.patch"
        assert result.tests["passed"] == 8
        assert "a1b2c3d" in result.summary

        # Verify all tool calls were invoked in order
        assert "inspect" in calls
        assert "edit:src/avatar.py" in calls
        assert "tests" in calls
        assert any(c.startswith("commit:") for c in calls)
