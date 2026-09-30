"""Tests for M77 — Master Agent Test Suite.

Mandatory validations per M77 specification for each of the 5 agents:
(CodingAgent, ResearchAgent, TestingAgent, ReviewerAgent, VisionAgent)
1. Task Context: Ingestion of task title, description, files, and parameters.
2. Tool Permissions: Verification that unauthorized tools are rejected with PermissionError.
3. Expected Tool Sequence: Deterministic sequence of tool calls matching agent role.
4. Failure Handling: Graceful degradation to FAILED status upon tool errors without process crashes.
5. Human Request: Detection of ambiguous context or explicit requirement yielding NEEDS_HUMAN_INPUT.
6. Final Result: Generation of conforming AgentResult (status, summary, artifacts, metrics).
"""

from typing import Any

import pytest

from agents.coding_agent import CodingAgent
from agents.protocol import AgentExecutionStatus, TaskContext
from agents.research_agent import ResearchAgent
from agents.reviewer_agent import ReviewerAgent
from agents.testing_agent import TestingAgent
from agents.vision_agent import VisionAgent

# ─── 1. Coding Agent Suite ─────────────────────────────────────────────────


class TestCodingAgentM77:
    """Deterministic validation of CodingAgent."""

    @pytest.mark.asyncio
    async def test_coding_agent_task_context(self) -> None:
        agent = CodingAgent()
        ctx = TaskContext(
            task_id="t-code-ctx",
            project_id="p-1",
            title="Refactor auth middleware",
            description="Replace legacy token parser with OIDC parser",
            files=["apps/backend/app/auth/oidc.py"],
            parameters={"target_env": "production"},
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert "Refactor auth middleware" in res.summary
        assert "apps/backend/app/auth/oidc.py" in res.changed_files

    @pytest.mark.asyncio
    async def test_coding_agent_tool_permissions(self) -> None:
        # Agent configured with permission only for inspect_files and edit_file
        agent = CodingAgent(
            tools={"inspect_files": lambda **kw: {}, "deploy_prod": lambda **kw: {}},
            allowed_tools={"inspect_files", "edit_file"},
        )
        with pytest.raises(PermissionError, match="not permitted"):
            await agent._call_tool("deploy_prod")

    @pytest.mark.asyncio
    async def test_coding_agent_expected_tool_sequence(self) -> None:
        sequence: list[str] = []

        async def mock_inspect(**kw: str) -> dict[str, str]:
            sequence.append("inspect_files")
            return {"src/app.py": "code"}

        async def mock_edit(**kw: str) -> bool:
            sequence.append("edit_file")
            return True

        async def mock_run_tests(**kw: str) -> dict[str, int]:
            sequence.append("run_tests")
            return {"passed": 5, "failed": 0, "total": 5}

        async def mock_commit(**kw: str) -> dict[str, str]:
            sequence.append("commit")
            return {"sha": "sha-c0ffee1"}

        agent = CodingAgent(
            tools={
                "inspect_files": mock_inspect,
                "edit_file": mock_edit,
                "run_tests": mock_run_tests,
                "commit": mock_commit,
            }
        )
        ctx = TaskContext(
            task_id="t-seq",
            project_id="p-1",
            title="Update handler",
            files=["src/app.py"],
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert sequence == ["inspect_files", "edit_file", "run_tests", "commit"]

    @pytest.mark.asyncio
    async def test_coding_agent_failure_handling(self) -> None:
        async def failing_tool(**kw: str) -> None:
            raise RuntimeError("Disk full / I/O error during file edit")

        agent = CodingAgent(tools={"edit_file": failing_tool})
        ctx = TaskContext(task_id="t-fail", project_id="p-1", title="Edit file")
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.FAILED
        assert "Task execution failed" in res.summary
        assert "Disk full" in res.summary

    @pytest.mark.asyncio
    async def test_coding_agent_human_request(self) -> None:
        agent = CodingAgent()
        ctx = TaskContext(
            task_id="t-human",
            project_id="p-1",
            title="Please clarify database schema requirement",
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert res.human_request is not None
        assert "Clarification requested" in res.human_request["prompt"]

    @pytest.mark.asyncio
    async def test_coding_agent_final_result_schema(self) -> None:
        agent = CodingAgent()
        ctx = TaskContext(task_id="t-res", project_id="p-1", title="Build parser")
        res = await agent.execute(ctx)
        d = res.to_dict()
        assert d["status"] == "SUCCESS"
        assert isinstance(d["artifacts"], list)
        assert len(d["artifacts"]) > 0
        assert d["artifacts"][0]["type"] == "diff"


# ─── 2. Research Agent Suite ───────────────────────────────────────────────


class TestResearchAgentM77:
    """Deterministic validation of ResearchAgent."""

    @pytest.mark.asyncio
    async def test_research_agent_task_context(self) -> None:
        agent = ResearchAgent()
        ctx = TaskContext(
            task_id="t-res-ctx",
            project_id="p-1",
            title="Compare Redis Streams vs NATS JetStream",
            description="Evaluate throughput, persistence guarantees, and ordering",
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert "Compare Redis Streams vs NATS JetStream" in res.summary

    @pytest.mark.asyncio
    async def test_research_agent_tool_permissions(self) -> None:
        agent = ResearchAgent(
            tools={"web_search": lambda **kw: [], "delete_cluster": lambda **kw: None},
            allowed_tools={"web_search", "search_docs"},
        )
        with pytest.raises(PermissionError, match="not permitted"):
            await agent._call_tool("delete_cluster")

    @pytest.mark.asyncio
    async def test_research_agent_expected_tool_sequence(self) -> None:
        tool_order: list[str] = []

        async def mock_search(**kw: str) -> list[dict[str, str]]:
            tool_order.append("web_search")
            return [
                {
                    "url": "https://docs.nats.io",
                    "title": "NATS JetStream Documentation",
                    "content": "JetStream provides at-least-once and exactly-once messaging semantics.",
                }
            ]

        agent = ResearchAgent(tools={"web_search": mock_search})
        ctx = TaskContext(task_id="t-seq-res", project_id="p-1", title="Study NATS JetStream")
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert tool_order == ["web_search"]
        assert len(res.artifacts) == 1
        assert res.artifacts[0]["type"] == "research_findings"

    @pytest.mark.asyncio
    async def test_research_agent_failure_handling(self) -> None:
        async def failing_search(**kw: str) -> None:
            raise ConnectionError("DNS resolution failed for search endpoint")

        agent = ResearchAgent(tools={"web_search": failing_search})
        ctx = TaskContext(task_id="t-res-fail", project_id="p-1", title="Web research")
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.FAILED
        assert "Task execution failed" in res.summary
        assert "DNS resolution failed" in res.summary

    @pytest.mark.asyncio
    async def test_research_agent_human_request(self) -> None:
        agent = ResearchAgent()
        ctx = TaskContext(
            task_id="t-res-human",
            project_id="p-1",
            title="Ambiguous research topic: please clarify target cloud provider",
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert res.human_request is not None

    @pytest.mark.asyncio
    async def test_research_agent_final_result_schema(self) -> None:
        agent = ResearchAgent()
        ctx = TaskContext(task_id="t-res-schema", project_id="p-1", title="Database benchmarks")
        res = await agent.execute(ctx)
        d = res.to_dict()
        assert d["status"] == "SUCCESS"
        assert "artifacts" in d
        assert d["artifacts"][0]["content"]["query"] == "Database benchmarks"


# ─── 3. Testing Agent Suite ────────────────────────────────────────────────


class TestTestingAgentM77:
    """Deterministic validation of TestingAgent."""

    @pytest.mark.asyncio
    async def test_testing_agent_task_context(self) -> None:
        agent = TestingAgent()
        ctx = TaskContext(
            task_id="t-test-ctx",
            project_id="p-1",
            title="Execute auth service tests",
            files=["tests/test_auth.py"],
            parameters={"generate_tests": True},
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert "Execute auth service tests" in res.summary
        assert any(a["name"] == "generated_tests.py" for a in res.artifacts)

    @pytest.mark.asyncio
    async def test_testing_agent_tool_permissions(self) -> None:
        agent = TestingAgent(
            tools={"run_pytest": lambda **kw: {}, "drop_database": lambda **kw: None},
            allowed_tools={"run_pytest"},
        )
        with pytest.raises(PermissionError, match="not permitted"):
            await agent._call_tool("drop_database")

    @pytest.mark.asyncio
    async def test_testing_agent_expected_tool_sequence(self) -> None:
        called: list[str] = []

        async def mock_pytest(**kw: str) -> dict[str, Any]:
            called.append("run_pytest")
            return {"passed": 12, "failed": 0, "skipped": 0, "duration_seconds": 0.42}

        agent = TestingAgent(tools={"run_pytest": mock_pytest})
        ctx = TaskContext(task_id="t-tseq", project_id="p-1", title="Run test suite", files=["tests/test_api.py"])
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert called == ["run_pytest"]
        assert res.tests["passed"] == 12

    @pytest.mark.asyncio
    async def test_testing_agent_failure_handling(self) -> None:
        async def failing_pytest(**kw: str) -> None:
            raise TimeoutError("Test suite timed out after 300 seconds")

        agent = TestingAgent(tools={"run_pytest": failing_pytest})
        ctx = TaskContext(task_id="t-tfail", project_id="p-1", title="Execute tests")
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.FAILED
        assert "timed out after 300 seconds" in res.summary

    @pytest.mark.asyncio
    async def test_testing_agent_human_request(self) -> None:
        agent = TestingAgent()
        ctx = TaskContext(
            task_id="t-thuman",
            project_id="p-1",
            title="Need to clarify integration test credentials",
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert res.human_request is not None

    @pytest.mark.asyncio
    async def test_testing_agent_final_result_schema(self) -> None:
        agent = TestingAgent()
        ctx = TaskContext(task_id="t-tschema", project_id="p-1", title="Run tests")
        res = await agent.execute(ctx)
        d = res.to_dict()
        assert d["status"] in ("SUCCESS", "FAILED")
        assert "tests" in d
        assert "artifacts" in d


# ─── 4. Reviewer Agent Suite ───────────────────────────────────────────────


class TestReviewerAgentM77:
    """Deterministic validation of ReviewerAgent."""

    @pytest.mark.asyncio
    async def test_reviewer_agent_task_context(self) -> None:
        agent = ReviewerAgent()
        ctx = TaskContext(
            task_id="t-rev-ctx",
            project_id="p-1",
            title="Review PR #42 User Profile",
            description="Review PR changes for security and completeness",
            files=["apps/backend/app/api/v1/user.py", "tests/test_users.py"],
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert "Review completed for 'Review PR #42 User Profile'" in res.summary
        assert res.artifacts[0]["type"] == "code_review"

    @pytest.mark.asyncio
    async def test_reviewer_agent_tool_permissions(self) -> None:
        agent = ReviewerAgent(
            tools={"get_diff": lambda **kw: "", "force_merge": lambda **kw: None},
            allowed_tools={"get_diff", "inspect_code"},
        )
        with pytest.raises(PermissionError, match="not permitted"):
            await agent._call_tool("force_merge")

    @pytest.mark.asyncio
    async def test_reviewer_agent_expected_tool_sequence(self) -> None:
        invocations: list[str] = []

        async def mock_diff(**kw: str) -> str:
            invocations.append("get_diff")
            return "+ new line"

        async def mock_inspect(**kw: str) -> str:
            invocations.append("inspect_code")
            return "code content"

        agent = ReviewerAgent(tools={"get_diff": mock_diff, "inspect_code": mock_inspect})
        ctx = TaskContext(task_id="t-rseq", project_id="p-1", title="Review changeset", files=["src/auth.py", "tests/test_auth.py"])
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert invocations == ["get_diff", "inspect_code"]

    @pytest.mark.asyncio
    async def test_reviewer_agent_failure_handling(self) -> None:
        async def failing_diff(**kw: str) -> None:
            raise KeyError("Git revision not found in repository")

        agent = ReviewerAgent(tools={"get_diff": failing_diff})
        ctx = TaskContext(task_id="t-rfail", project_id="p-1", title="Review patch")
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.FAILED
        assert "Git revision not found" in res.summary

    @pytest.mark.asyncio
    async def test_reviewer_agent_human_request(self) -> None:
        agent = ReviewerAgent()
        ctx = TaskContext(
            task_id="t-rhuman",
            project_id="p-1",
            title="Please clarify security requirement for review",
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert res.human_request is not None

    @pytest.mark.asyncio
    async def test_reviewer_agent_final_result_schema(self) -> None:
        agent = ReviewerAgent()
        ctx = TaskContext(task_id="t-rschema", project_id="p-1", title="Code review")
        res = await agent.execute(ctx)
        d = res.to_dict()
        assert d["status"] == "SUCCESS"
        assert d["artifacts"][0]["content"]["verdict"] in ("APPROVED", "CHANGES_REQUESTED")


# ─── 5. Vision Agent Suite ─────────────────────────────────────────────────


class TestVisionAgentM77:
    """Deterministic validation of VisionAgent."""

    @pytest.mark.asyncio
    async def test_vision_agent_task_context(self) -> None:
        agent = VisionAgent()
        ctx = TaskContext(
            task_id="t-vis-ctx",
            project_id="p-1",
            title="Inspect dashboard screenshot",
            files=["ui_dashboard.png"],
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert "Completed visual analysis on image 'ui_dashboard.png'" in res.summary

    @pytest.mark.asyncio
    async def test_vision_agent_tool_permissions(self) -> None:
        agent = VisionAgent(
            tools={"analyze_visual": lambda **kw: {}, "format_drive": lambda **kw: None},
            allowed_tools={"analyze_visual", "extract_ocr"},
        )
        with pytest.raises(PermissionError, match="not permitted"):
            await agent._call_tool("format_drive")

    @pytest.mark.asyncio
    async def test_vision_agent_expected_tool_sequence(self) -> None:
        called_tools: list[str] = []

        async def mock_vis_tool(**kw: str) -> dict[str, Any]:
            called_tools.append("analyze_visual")
            return {
                "description": "Mock visual description",
                "detected_elements": ["Button", "Input", "Navbar"],
                "extracted_text": "Sign In",
                "ui_defects": [],
                "metadata": {"width": 1024, "height": 768},
            }

        agent = VisionAgent(tools={"analyze_visual": mock_vis_tool})
        ctx = TaskContext(task_id="t-vseq", project_id="p-1", title="Analyze UI", files=["mock_ui.png"])
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.SUCCESS
        assert called_tools == ["analyze_visual"]
        assert len(res.artifacts) == 1
        assert res.artifacts[0]["type"] == "visual_analysis"

    @pytest.mark.asyncio
    async def test_vision_agent_failure_handling(self) -> None:
        async def failing_vis(**kw: str) -> None:
            raise ValueError("Corrupted image header or unsupported pixel format")

        agent = VisionAgent(tools={"analyze_visual": failing_vis})
        ctx = TaskContext(task_id="t-vfail", project_id="p-1", title="Analyze corrupted image", files=["corrupt.png"])
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.FAILED
        assert "Corrupted image header" in res.summary

    @pytest.mark.asyncio
    async def test_vision_agent_human_request(self) -> None:
        agent = VisionAgent()
        ctx = TaskContext(
            task_id="t-vhuman",
            project_id="p-1",
            title="Ask user to clarify blurry image regions",
        )
        res = await agent.execute(ctx)
        assert res.status == AgentExecutionStatus.NEEDS_HUMAN_INPUT
        assert res.human_request is not None

    @pytest.mark.asyncio
    async def test_vision_agent_final_result_schema(self) -> None:
        agent = VisionAgent()
        ctx = TaskContext(task_id="t-vschema", project_id="p-1", title="Analyze diagram", files=["arch.svg"])
        res = await agent.execute(ctx)
        d = res.to_dict()
        assert d["status"] == "SUCCESS"
        assert d["artifacts"][0]["content"]["media_type"] == "image"
        assert "detected_elements" in d["artifacts"][0]["content"]
