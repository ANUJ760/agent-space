"""Tests for M39 — Testing Agent.

Validates:
- TestingAgent metadata, role, and capabilities
- Test execution interface and summary statistics
- Failure reproduction and stack trace analysis
- Optional test generation when requested
"""

from agents.protocol import AgentExecutionStatus, TaskContext
from agents.testing_agent import TestingAgent


class TestTestingAgent:
    def test_agent_initialization(self) -> None:
        agent = TestingAgent(name="PytestRunner")
        assert agent.name == "PytestRunner"
        assert agent.role == "TESTER"
        assert "python" in agent.capabilities

    async def test_passing_test_suite_execution(self) -> None:
        async def mock_run_pytest(targets: list[str]) -> dict[str, int | float | list]:
            return {
                "passed": 42,
                "failed": 0,
                "skipped": 2,
                "duration_seconds": 2.15,
                "failures": [],
            }

        agent = TestingAgent(tools={"run_pytest": mock_run_pytest})
        ctx = TaskContext(
            task_id="t-test-1",
            project_id="p-1",
            title="Run regression tests",
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert result.tests["passed"] == 42
        assert result.tests["failed"] == 0
        assert len(result.artifacts) == 1
        assert result.artifacts[0]["name"] == "test_report.json"

    async def test_failing_test_reproduction(self) -> None:
        async def mock_run_pytest(targets: list[str]) -> dict[str, int | float | list]:
            return {
                "passed": 10,
                "failed": 2,
                "skipped": 0,
                "duration_seconds": 0.95,
                "failures": [
                    {
                        "name": "test_auth_expiry",
                        "file": "tests/test_auth.py",
                        "error": "AssertionError: Token expired 401 != 200",
                    },
                    {
                        "name": "test_token_refresh",
                        "file": "tests/test_auth.py",
                        "error": "KeyError: 'refresh_token'",
                    },
                ],
            }

        agent = TestingAgent(tools={"run_pytest": mock_run_pytest})
        ctx = TaskContext(
            task_id="t-test-2",
            project_id="p-1",
            title="Verify authentication test suite",
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.FAILED
        assert result.tests["failed"] == 2

        report = result.artifacts[0]["content"]
        assert len(report["failures"]) == 2
        assert report["failures"][0]["test_name"] == "test_auth_expiry"
        assert report["failures"][0]["reproducible"] is True

    async def test_optional_test_generation(self) -> None:
        agent = TestingAgent()
        ctx = TaskContext(
            task_id="t-test-gen-3",
            project_id="p-1",
            title="Generate tests for auth module",
            parameters={"generate_tests": True},
        )

        result = await agent.execute(ctx)
        artifact_names = [a["name"] for a in result.artifacts]
        assert "generated_tests.py" in artifact_names
        gen_art = next(a for a in result.artifacts if a["name"] == "generated_tests.py")
        assert "def test_t_test_gen_3_generated" in gen_art["content"]
