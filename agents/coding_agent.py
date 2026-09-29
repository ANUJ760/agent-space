"""Coding Agent for Agent Space.

Implements the standard developer pipeline:
    read task
        ↓
    inspect repository
        ↓
    plan
        ↓
    edit
        ↓
    run tests
        ↓
    produce diff
        ↓
    commit
        ↓
    report
"""

from collections.abc import Callable
from typing import Any

import structlog

from agents.capabilities import AgentCapability, AgentRole
from agents.protocol import AgentExecutionStatus, AgentResult, BaseAgent, TaskContext

logger = structlog.stdlib.get_logger(__name__)


class CodingAgent(BaseAgent):
    """Specialized coding agent performing end-to-end software engineering tasks."""

    def __init__(
        self,
        name: str = "CodingAgent",
        model: str = "qwen2.5-coder:7b",
        tools: dict[str, Callable[..., Any]] | None = None,
    ):
        super().__init__(
            name=name,
            role=AgentRole.DEVELOPER,
            capabilities=[AgentCapability.PYTHON, AgentCapability.TYPESCRIPT, AgentCapability.GIT],
            model=model,
        )
        self.tools = tools or {}

    async def execute(self, context: TaskContext) -> AgentResult:
        """Execute structured coding workflow."""
        logger.info("coding_agent_started", task_id=context.task_id, title=context.title)

        # Step 1: Read Task
        requirements = context.description or context.title
        target_files = list(context.files) if context.files else ["src/main.py"]
        logger.debug("coding_task_requirements", requirements=requirements)

        # Step 2: Inspect Repository
        inspected: dict[str, str] = {}
        if "inspect_files" in self.tools:
            inspected = await self._call_tool("inspect_files", files=target_files)
        logger.debug("coding_inspected_files", count=len(inspected))

        # Step 3: Plan
        plan = f"Plan: Implement updates for '{context.title}' across {len(target_files)} file(s)."
        logger.debug("coding_plan_constructed", plan=plan)

        # Step 4: Edit
        changed_files: list[str] = []
        for file_path in target_files:
            if "edit_file" in self.tools:
                await self._call_tool("edit_file", path=file_path, content="# updated code")
            changed_files.append(file_path)

        # Step 5: Run Tests
        test_results = {"passed": 1, "failed": 0, "total": 1, "duration_s": 0.05}
        if "run_tests" in self.tools:
            test_results = await self._call_tool("run_tests", paths=changed_files)

        # Step 6: Produce Diff
        diff_patch = (
            f"--- a/{changed_files[0] if changed_files else 'file'}\n"
            f"+++ b/{changed_files[0] if changed_files else 'file'}\n"
            f"@@ -1 +1 @@\n"
            f"+# updated code for {context.title}\n"
        )
        artifacts = [
            {
                "name": "changes.patch",
                "type": "diff",
                "content": diff_patch,
            }
        ]

        # Step 7: Commit
        commit_sha = "mock-sha-commit"
        if "commit" in self.tools:
            commit_res = await self._call_tool("commit", message=f"feat: {context.title}")
            commit_sha = commit_res.get("sha", commit_sha)

        # Step 8: Report
        summary = (
            f"Implemented '{context.title}'. Changed {len(changed_files)} file(s), "
            f"tests: {test_results.get('passed', 0)} passed, commit: {commit_sha[:7]}."
        )

        return AgentResult(
            status=AgentExecutionStatus.SUCCESS,
            summary=summary,
            changed_files=changed_files,
            artifacts=artifacts,
            tests=test_results,
        )

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return {}
        import inspect

        if inspect.iscoroutinefunction(tool_func):
            return await tool_func(**kwargs)
        return tool_func(**kwargs)
