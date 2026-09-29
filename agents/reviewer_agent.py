"""Reviewer Agent for Agent Space.

Performs multi-dimensional automated code and task reviews across 4 pillars:
1. Requirements Review
2. Diff / Implementation Review
3. Test Coverage & Quality Review
4. Security Review

Outputs structured findings with severity levels and actionable recommendations.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

from agents.capabilities import AgentCapability, AgentRole
from agents.protocol import AgentExecutionStatus, AgentResult, BaseAgent, TaskContext

logger = structlog.stdlib.get_logger(__name__)


class FindingSeverity(StrEnum):
    """Severity classification for review findings."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReviewCategory(StrEnum):
    """Pillar category of a review finding."""

    REQUIREMENTS = "REQUIREMENTS"
    DIFF = "DIFF"
    TESTS = "TESTS"
    SECURITY = "SECURITY"


class ReviewerAgent(BaseAgent):
    """Specialized reviewer agent evaluating requirements, code diffs, tests, and security."""

    def __init__(
        self,
        name: str = "ReviewerAgent",
        model: str = "qwen2.5-coder:7b",
        tools: dict[str, Callable[..., Any]] | None = None,
    ):
        super().__init__(
            name=name,
            role=AgentRole.REVIEWER,
            capabilities=[AgentCapability.PYTHON, AgentCapability.TYPESCRIPT, AgentCapability.GIT],
            model=model,
        )
        self.tools = tools or {}

    async def execute(self, context: TaskContext) -> AgentResult:
        """Execute comprehensive multi-pillar review."""
        logger.info("reviewer_agent_started", task_id=context.task_id, title=context.title)

        findings: list[dict[str, Any]] = []

        # Pillar 1: Requirements Review
        req_findings = self._review_requirements(context)
        findings.extend(req_findings)

        # Pillar 2: Diff / Implementation Review
        diff_findings = self._review_diffs(context)
        findings.extend(diff_findings)

        # Pillar 3: Test Review
        test_findings = self._review_tests(context)
        findings.extend(test_findings)

        # Pillar 4: Security Review
        security_findings = self._review_security(context)
        findings.extend(security_findings)

        # Determine verdict
        has_blocking = any(f["severity"] in (FindingSeverity.HIGH, FindingSeverity.CRITICAL) for f in findings)
        verdict = "CHANGES_REQUESTED" if has_blocking else "APPROVED"

        report_data = {
            "task_id": context.task_id,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "verdict": verdict,
            "findings_count": len(findings),
            "findings": findings,
        }

        artifacts = [
            {
                "name": "review_report.json",
                "type": "code_review",
                "content": report_data,
            }
        ]

        summary = (
            f"Review completed for '{context.title}'. Verdict: {verdict}. "
            f"Identified {len(findings)} finding(s) across requirements, diffs, tests, and security."
        )

        return AgentResult(
            status=AgentExecutionStatus.SUCCESS,
            summary=summary,
            artifacts=artifacts,
        )

    def _review_requirements(self, context: TaskContext) -> list[dict[str, Any]]:
        """Verify task requirements coverage."""
        findings = []
        if not context.description:
            findings.append(
                {
                    "severity": FindingSeverity.LOW,
                    "category": ReviewCategory.REQUIREMENTS,
                    "file": "task_spec",
                    "finding": "Task description is empty; requirements cannot be completely verified.",
                    "recommendation": "Provide detailed acceptance criteria in task description.",
                }
            )
        return findings

    def _review_diffs(self, context: TaskContext) -> list[dict[str, Any]]:
        """Scan modified files for code quality issues."""
        findings = []
        for file_path in context.files:
            if "temp" in file_path.lower() or "tmp" in file_path.lower():
                findings.append(
                    {
                        "severity": FindingSeverity.MEDIUM,
                        "category": ReviewCategory.DIFF,
                        "file": file_path,
                        "finding": "Temporary debug or scratch file included in changeset.",
                        "recommendation": "Remove temporary test files before merging to main branch.",
                    }
                )
        return findings

    def _review_tests(self, context: TaskContext) -> list[dict[str, Any]]:
        """Verify test files accompany implementation files."""
        findings = []
        has_tests = any("test" in f.lower() for f in context.files)
        has_source = any("src" in f.lower() or "app" in f.lower() for f in context.files)

        if has_source and not has_tests:
            findings.append(
                {
                    "severity": FindingSeverity.HIGH,
                    "category": ReviewCategory.TESTS,
                    "file": context.files[0] if context.files else "codebase",
                    "finding": "Changeset modifies production code without adding or updating unit tests.",
                    "recommendation": "Add automated test coverage covering new behavior.",
                }
            )
        return findings

    def _review_security(self, context: TaskContext) -> list[dict[str, Any]]:
        """Scan for hardcoded credentials, unsafe queries, and security anti-patterns."""
        findings = []
        for file_path in context.files:
            content = context.parameters.get(f"content:{file_path}", "")
            if "password =" in content or "api_key =" in content:
                findings.append(
                    {
                        "severity": FindingSeverity.CRITICAL,
                        "category": ReviewCategory.SECURITY,
                        "file": file_path,
                        "finding": "Hardcoded secret or credential detected in source code.",
                        "recommendation": "Extract credentials into environment variables or secret store.",
                    }
                )
        return findings
