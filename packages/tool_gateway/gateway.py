"""Tool Gateway providing secure, audited, authorized execution boundary for agents.

Every tool invocation strictly requires:
- tool_call_id: unique call identifier
- agent_id: calling agent identifier
- project_id: tenant project scope
- task_id: task execution context
- authorization: credentials/scopes
- timeout: maximum execution timeout in seconds

Authorization occurs strictly BEFORE execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


class ToolAuthorizationError(PermissionError):
    """Raised when an agent is not authorized to invoke a tool."""


class ToolExecutionTimeoutError(TimeoutError):
    """Raised when tool execution exceeds configured timeout."""


@dataclass
class ToolCallContext:
    """Security and execution context mandatory for every tool call."""

    tool_call_id: str
    agent_id: str
    project_id: str
    task_id: str
    authorization: dict[str, Any]
    timeout: float = 30.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ToolGateway:
    """Security boundary enforcing authorization, audit logging, and timeout limits on tool execution."""

    def __init__(self, sandbox_executor: Any = None):
        self.sandbox_executor = sandbox_executor
        self._tools: dict[str, Callable[..., Any]] = {}
        self._permissions_map: dict[str, set[str]] = {}
        self._register_default_tools()

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        required_permissions: set[str] | None = None,
    ) -> None:
        """Register a typed tool with its required permission scopes."""
        self._tools[name] = handler
        self._permissions_map[name] = required_permissions or set()

    def _register_default_tools(self) -> None:
        # File tools
        self.register_tool("read_file", self._read_file, {"file:read"})
        self.register_tool("write_file", self._write_file, {"file:write"})
        self.register_tool("delete_file", self._delete_file, {"file:write"})
        self.register_tool("list_files", self._list_files, {"file:read"})
        self.register_tool("search_files", self._search_files, {"file:read"})

        # Git tools
        self.register_tool("git_status", self._git_status, {"git:read"})
        self.register_tool("git_diff", self._git_diff, {"git:read"})
        self.register_tool("git_branch", self._git_branch, {"git:write"})
        self.register_tool("git_commit", self._git_commit, {"git:write"})

        # Execution tools
        self.register_tool("run_command", self._run_command, {"exec:command"})
        self.register_tool("run_tests", self._run_tests, {"exec:tests"})

        # Task & Human tools
        self.register_tool("get_task", self._get_task, {"task:read"})
        self.register_tool("update_task", self._update_task, {"task:write"})
        self.register_tool("create_task", self._create_task, {"task:write"})
        self.register_tool("request_human", self._request_human, {"human:request"})

        # Artifact tools
        self.register_tool("create_artifact", self._create_artifact, {"artifact:write"})
        self.register_tool("upload_artifact", self._upload_artifact, {"artifact:write"})

    def authorize(self, context: ToolCallContext, tool_name: str) -> None:
        """Validate context integrity and permissions before execution."""
        if not context.tool_call_id or not context.agent_id or not context.project_id or not context.task_id:
            raise ToolAuthorizationError("Missing mandatory context parameters (tool_call_id, agent_id, project_id, task_id)")

        if tool_name not in self._tools:
            raise ToolAuthorizationError(f"Unknown tool '{tool_name}'")

        required = self._permissions_map.get(tool_name, set())
        granted = set(context.authorization.get("scopes", []))

        # Check permission authorization
        if required and not required.issubset(granted) and "*" not in granted:
            logger.warning(
                "tool_authorization_denied",
                tool=tool_name,
                agent_id=context.agent_id,
                missing_scopes=list(required - granted),
            )
            raise ToolAuthorizationError(f"Agent unauthorized for tool '{tool_name}'. Missing scopes: {required - granted}")

    async def execute(self, context: ToolCallContext, tool_name: str, **kwargs: Any) -> Any:
        """Authorize and execute tool within security boundary and timeout constraint."""
        # 1. Authorize BEFORE execution
        self.authorize(context, tool_name)

        logger.info(
            "tool_execution_started",
            tool_call_id=context.tool_call_id,
            tool=tool_name,
            agent_id=context.agent_id,
            task_id=context.task_id,
        )

        handler = self._tools[tool_name]

        # 2. Execute under timeout
        try:
            async with asyncio.timeout(context.timeout):
                import inspect

                if inspect.iscoroutinefunction(handler):
                    return await handler(context, **kwargs)
                return handler(context, **kwargs)
        except TimeoutError as exc:
            logger.error("tool_execution_timeout", tool=tool_name, timeout=context.timeout)
            raise ToolExecutionTimeoutError(f"Tool '{tool_name}' timed out after {context.timeout}s") from exc

    # --------------------------------------------------------------------------
    # Default Tool Handlers
    # --------------------------------------------------------------------------

    async def _read_file(self, ctx: ToolCallContext, path: str) -> dict[str, Any]:
        return {"path": path, "content": f"# Content of {path}", "status": "ok"}

    async def _write_file(self, ctx: ToolCallContext, path: str, content: str) -> dict[str, Any]:
        return {"path": path, "bytes_written": len(content), "status": "ok"}

    async def _delete_file(self, ctx: ToolCallContext, path: str) -> dict[str, Any]:
        return {"path": path, "status": "deleted"}

    async def _list_files(self, ctx: ToolCallContext, directory: str = ".") -> list[str]:
        return ["src/main.py", "tests/test_main.py", "README.md"]

    async def _search_files(self, ctx: ToolCallContext, query: str, directory: str = ".") -> list[dict[str, Any]]:
        return [{"file": "src/main.py", "line": 42, "match": query}]

    async def _git_status(self, ctx: ToolCallContext) -> dict[str, Any]:
        return {"branch": "main", "clean": True, "staged": [], "modified": []}

    async def _git_diff(self, ctx: ToolCallContext) -> str:
        return "diff --git a/file b/file\n+updated"

    async def _git_branch(self, ctx: ToolCallContext, branch_name: str | None = None) -> dict[str, Any]:
        return {"active_branch": branch_name or "main"}

    async def _git_commit(self, ctx: ToolCallContext, message: str) -> dict[str, Any]:
        return {"sha": "c0ffee1234567890", "message": message}

    async def _run_command(self, ctx: ToolCallContext, command: str) -> dict[str, Any]:
        return {"stdout": f"Executed: {command}", "stderr": "", "exit_code": 0}

    async def _run_tests(self, ctx: ToolCallContext, targets: list[str] | None = None) -> dict[str, Any]:
        return {"passed": 10, "failed": 0, "total": 10, "exit_code": 0}

    async def _get_task(self, ctx: ToolCallContext) -> dict[str, Any]:
        return {"task_id": ctx.task_id, "project_id": ctx.project_id, "status": "IN_PROGRESS"}

    async def _update_task(self, ctx: ToolCallContext, **kwargs: Any) -> dict[str, Any]:
        return {"task_id": ctx.task_id, "updated": True, "fields": kwargs}

    async def _create_task(self, ctx: ToolCallContext, title: str, priority: str = "MEDIUM") -> dict[str, Any]:
        return {"id": "new-task-1", "title": title, "priority": priority}

    async def _request_human(self, ctx: ToolCallContext, question: str, options: list[str] | None = None) -> dict[str, Any]:
        return {"question": question, "options": options or [], "status": "SUBMITTED"}

    async def _create_artifact(self, ctx: ToolCallContext, name: str, type: str, content: Any) -> dict[str, Any]:
        return {"artifact_id": "art-1", "name": name, "type": type}

    async def _upload_artifact(self, ctx: ToolCallContext, artifact_id: str, data: bytes) -> dict[str, Any]:
        return {"artifact_id": artifact_id, "size_bytes": len(data), "status": "UPLOADED"}
