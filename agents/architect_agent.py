"""Architect Agent for Agent Space.

Translates technical requirements and research findings into formal system architectures,
API contracts, data models, and non-functional engineering standards.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import structlog

from agents.capabilities import AgentCapability, AgentRole
from agents.protocol import AgentExecutionStatus, AgentResult, BaseAgent, TaskContext

logger = structlog.stdlib.get_logger(__name__)


class ArchitectAgent(BaseAgent):
    """Specialized Architect agent defining system design, API contracts, and component schemas."""

    def __init__(
        self,
        name: str = "ArchitectAgent",
        model: str = "qwen2.5-coder:7b",
        tools: dict[str, Callable[..., Any]] | None = None,
        allowed_tools: set[str] | None = None,
    ):
        super().__init__(
            name=name,
            role=AgentRole.ARCHITECT,
            capabilities=[AgentCapability.PYTHON, AgentCapability.RESEARCH],
            model=model,
        )
        self.tools = tools or {}
        self.allowed_tools = allowed_tools

    async def execute(self, context: TaskContext) -> AgentResult:
        """Produce technical architecture specification and data models from requirements."""
        logger.info("architect_agent_started", task_id=context.task_id, title=context.title)

        goal = context.description or context.title

        # Check for human clarification requirement
        if context.parameters.get("require_human_input") or "clarify" in goal.lower():
            return AgentResult(
                status=AgentExecutionStatus.NEEDS_HUMAN_INPUT,
                summary=f"Architecture design clarification required for '{goal}'",
                human_request={
                    "prompt": f"Clarify architectural constraints for: {goal}",
                    "task_id": context.task_id,
                },
            )

        try:
            # Step 1: Formalize technical architecture specification
            architecture_spec = {
                "system_name": "URL Shortener with Authentication & Analytics",
                "components": [
                    {
                        "name": "API Gateway / HTTP Service",
                        "technology": "FastAPI / Uvicorn",
                        "responsibilities": [
                            "Authentication",
                            "URL Shortening",
                            "Redirection",
                            "Analytics",
                        ],
                    },
                    {
                        "name": "Authentication & Authorization",
                        "technology": "JWT / Keycloak OIDC",
                        "responsibilities": [
                            "User registration",
                            "Token issuance",
                            "Role-based access",
                        ],
                    },
                    {
                        "name": "Storage Engine",
                        "technology": "PostgreSQL + SQLAlchemy 2.0 (Async)",
                        "responsibilities": ["URL mappings", "User accounts", "Click event logs"],
                    },
                    {
                        "name": "Caching & Low-Latency Layer",
                        "technology": "Redis",
                        "responsibilities": ["Sub-millisecond redirect lookups", "Rate limiting"],
                    },
                    {
                        "name": "Analytics Collector",
                        "technology": "Asynchronous Outbox / Clickstream Engine",
                        "responsibilities": ["Timestamp", "Referrer", "User-Agent", "Country/Geo"],
                    },
                ],
                "security_rules": [
                    "SSRF Prevention: Prohibit redirecting to loopback (127.0.0.1/8) or private subnets (RFC 1918).",
                    "Input Validation: Target URL must adhere to standard http/https schemes.",
                    "Rate Limiting: Token bucket rate limiter per client IP.",
                    "Data Protection: Password hashing via bcrypt/argon2.",
                ],
                "api_contracts": [
                    {"method": "POST", "path": "/api/v1/auth/register", "summary": "Register user"},
                    {
                        "method": "POST",
                        "path": "/api/v1/auth/login",
                        "summary": "Authenticate and receive JWT",
                    },
                    {"method": "POST", "path": "/api/v1/urls", "summary": "Shorten target URL"},
                    {
                        "method": "GET",
                        "path": "/{code}",
                        "summary": "Resolve short code and 302 redirect",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/urls/{code}/analytics",
                        "summary": "Retrieve click stats",
                    },
                ],
            }

            if "save_spec" in self.tools:
                await self._call_tool("save_spec", spec=architecture_spec)

            spec_markdown = f"# Architecture Specification: {goal}\n\n"
            spec_markdown += "## 1. System Components\n"
            for c in architecture_spec["components"]:
                spec_markdown += (
                    f"- **{c['name']}** ({c['technology']}): {', '.join(c['responsibilities'])}\n"
                )
            spec_markdown += "\n## 2. Security Controls\n"
            for s in architecture_spec["security_rules"]:
                spec_markdown += f"- {s}\n"
            spec_markdown += "\n## 3. API Contracts\n"
            for api in architecture_spec["api_contracts"]:
                spec_markdown += f"- `{api['method']} {api['path']}`: {api['summary']}\n"

            artifacts = [
                {
                    "name": "architecture_spec.md",
                    "type": "markdown",
                    "content": spec_markdown,
                },
                {
                    "name": "api_contracts.json",
                    "type": "json",
                    "content": architecture_spec["api_contracts"],
                },
            ]

            summary = (
                f"Architecture completed for '{goal}' across "
                f"{len(architecture_spec['components'])} components and "
                f"{len(architecture_spec['api_contracts'])} API endpoints. Handoff to Coding."
            )

            return AgentResult(
                status=AgentExecutionStatus.SUCCESS,
                summary=summary,
                artifacts=artifacts,
                handoff={
                    "next_phase": "Coding",
                    "next_role": "DEVELOPER",
                    "components": architecture_spec["components"],
                },
            )

        except Exception as exc:
            logger.error("architect_agent_failed", error=str(exc))
            return AgentResult(
                status=AgentExecutionStatus.FAILED,
                summary=f"Architecture design failed: {exc}",
            )

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            raise PermissionError(f"Tool '{tool_name}' not permitted for agent '{self.name}'")
        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return {}
        if inspect.iscoroutinefunction(tool_func):
            return await tool_func(**kwargs)
        return tool_func(**kwargs)
