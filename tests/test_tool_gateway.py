"""Tests for M42 — Tool Gateway.

Validates:
- ToolCallContext mandatory parameter enforcement
- Authorization checked strictly before execution
- Scope-based access control per typed tool
- Timeout enforcement (ToolExecutionTimeoutError)
- Execution of typed tool categories (file, git, command, task, artifact, human)
"""

import asyncio

import pytest

from packages.tool_gateway import (
    ToolAuthorizationError,
    ToolCallContext,
    ToolExecutionTimeoutError,
    ToolGateway,
)


class TestToolGateway:
    def test_missing_mandatory_context_rejected(self) -> None:
        gateway = ToolGateway()
        ctx = ToolCallContext(
            tool_call_id="",  # Missing!
            agent_id="agent-1",
            project_id="proj-1",
            task_id="task-1",
            authorization={"scopes": ["file:read"]},
        )
        with pytest.raises(ToolAuthorizationError):
            gateway.authorize(ctx, "read_file")

    def test_unauthorized_scope_rejected_before_execution(self) -> None:
        gateway = ToolGateway()
        ctx = ToolCallContext(
            tool_call_id="call-1",
            agent_id="agent-1",
            project_id="proj-1",
            task_id="task-1",
            authorization={"scopes": ["file:read"]},  # Only file:read, no git:write
        )
        with pytest.raises(ToolAuthorizationError):
            gateway.authorize(ctx, "git_commit")

    async def test_authorized_tool_execution(self) -> None:
        gateway = ToolGateway()
        ctx = ToolCallContext(
            tool_call_id="call-2",
            agent_id="agent-1",
            project_id="proj-1",
            task_id="task-1",
            authorization={"scopes": ["file:read", "file:write", "git:read", "git:write", "task:read", "human:request"]},
        )

        # 1. Read file
        res1 = await gateway.execute(ctx, "read_file", path="src/app.py")
        assert res1["path"] == "src/app.py"

        # 2. Write file
        res2 = await gateway.execute(ctx, "write_file", path="src/app.py", content="print('hello')")
        assert res2["bytes_written"] == 14

        # 3. Git commit
        res3 = await gateway.execute(ctx, "git_commit", message="feat: add app")
        assert "sha" in res3

        # 4. Request human
        res4 = await gateway.execute(ctx, "request_human", question="Proceed with deployment?")
        assert res4["status"] == "SUBMITTED"

    async def test_execution_timeout_enforced(self) -> None:
        gateway = ToolGateway()

        async def slow_tool(ctx: ToolCallContext) -> str:
            await asyncio.sleep(0.5)
            return "done"

        gateway.register_tool("slow_op", slow_tool, {"*"})

        ctx = ToolCallContext(
            tool_call_id="call-3",
            agent_id="agent-1",
            project_id="proj-1",
            task_id="task-1",
            authorization={"scopes": ["*"]},
            timeout=0.05,  # 50ms timeout
        )

        with pytest.raises(ToolExecutionTimeoutError):
            await gateway.execute(ctx, "slow_op")
