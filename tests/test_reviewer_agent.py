"""Tests for M40 — Reviewer Agent.

Validates:
- ReviewerAgent metadata, role, and capabilities
- Clean review verdict (APPROVED)
- Missing tests detection (HIGH severity -> CHANGES_REQUESTED)
- Security vulnerability detection (CRITICAL severity -> CHANGES_REQUESTED)
- Structured findings schema compliance (severity, category, file, finding, recommendation)
"""

from agents.protocol import AgentExecutionStatus, TaskContext
from agents.reviewer_agent import FindingSeverity, ReviewCategory, ReviewerAgent


class TestReviewerAgent:
    def test_agent_initialization(self) -> None:
        agent = ReviewerAgent(name="CodeAuditor")
        assert agent.name == "CodeAuditor"
        assert agent.role == "REVIEWER"
        assert "git" in agent.capabilities

    async def test_clean_review_approved(self) -> None:
        agent = ReviewerAgent()
        ctx = TaskContext(
            task_id="t-rev-1",
            project_id="p-1",
            title="Clean refactor with tests",
            description="Refactored database pool with 100% test coverage",
            files=["src/db.py", "tests/test_db.py"],
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        report = result.artifacts[0]["content"]
        assert report["verdict"] == "APPROVED"
        assert report["findings_count"] == 0

    async def test_missing_tests_changes_requested(self) -> None:
        agent = ReviewerAgent()
        ctx = TaskContext(
            task_id="t-rev-2",
            project_id="p-1",
            title="Add user payment endpoint",
            description="Added endpoint in src/payment.py",
            files=["src/payment.py"],  # No test file!
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        report = result.artifacts[0]["content"]
        assert report["verdict"] == "CHANGES_REQUESTED"

        findings = report["findings"]
        test_finding = next(f for f in findings if f["category"] == ReviewCategory.TESTS)
        assert test_finding["severity"] == FindingSeverity.HIGH
        assert "without adding or updating unit tests" in test_finding["finding"]

    async def test_security_vulnerability_critical(self) -> None:
        agent = ReviewerAgent()
        ctx = TaskContext(
            task_id="t-rev-3",
            project_id="p-1",
            title="Integrate stripe api",
            description="Stripe integration",
            files=["src/stripe_client.py", "tests/test_stripe.py"],
            parameters={"content:src/stripe_client.py": 'api_key = "sk_live_123456789"'},
        )

        result = await agent.execute(ctx)
        report = result.artifacts[0]["content"]
        assert report["verdict"] == "CHANGES_REQUESTED"

        sec_finding = next(f for f in report["findings"] if f["category"] == ReviewCategory.SECURITY)
        assert sec_finding["severity"] == FindingSeverity.CRITICAL
        assert "Hardcoded secret" in sec_finding["finding"]
        assert "environment variables" in sec_finding["recommendation"]
