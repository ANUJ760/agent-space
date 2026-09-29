"""Sandbox abstraction and manager for isolated execution."""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import structlog

from packages.sandbox.policy import SandboxPolicy

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class SandboxExecutionResult:
    """Execution output from a sandboxed command."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    killed: bool = False
    peak_memory_mb: float = 0.0
    error_message: str | None = None


class Sandbox(ABC):
    """Abstract interface defining the lifecycle of a sandboxed execution runtime."""

    @abstractmethod
    async def create(self, policy: SandboxPolicy) -> str:
        """Create and initialize an isolated sandbox instance. Returns sandbox_id."""
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self,
        sandbox_id: str,
        command: str | list[str],
        timeout: float | None = None,
    ) -> SandboxExecutionResult:
        """Execute command within the sandbox under enforced policy limits."""
        raise NotImplementedError

    @abstractmethod
    async def destroy(self, sandbox_id: str) -> bool:
        """Terminate and clean up sandbox instance."""
        raise NotImplementedError


class MockSandbox(Sandbox):
    """Safe in-memory mock sandbox implementing full lifecycle and policy checks."""

    def __init__(self) -> None:
        self.sandboxes: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create(self, policy: SandboxPolicy) -> str:
        policy.validate()
        sandbox_id = f"sbx-{uuid.uuid4().hex[:8]}"
        async with self._lock:
            self.sandboxes[sandbox_id] = {
                "id": sandbox_id,
                "policy": policy,
                "created_at": time.time(),
                "status": "READY",
            }
        logger.info("mock_sandbox_created", sandbox_id=sandbox_id, uid=policy.run_as_uid)
        return sandbox_id

    async def execute(
        self,
        sandbox_id: str,
        command: str | list[str],
        timeout: float | None = None,
    ) -> SandboxExecutionResult:
        async with self._lock:
            sbx = self.sandboxes.get(sandbox_id)
            if not sbx:
                raise KeyError(f"Sandbox '{sandbox_id}' not found")

        policy: SandboxPolicy = sbx["policy"]
        effective_timeout = timeout or policy.timeout_seconds
        cmd_str = command if isinstance(command, str) else " ".join(command)
        logger.debug("executing_in_sandbox", sandbox_id=sandbox_id, timeout=effective_timeout)

        # Enforce security policies: Disallow root / sudo commands
        if "sudo" in cmd_str.lower() or "su -" in cmd_str.lower():
            return SandboxExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Permission denied: Root privilege escalation is strictly forbidden",
                duration_seconds=0.01,
                error_message="Privilege escalation blocked",
            )

        start = time.monotonic()
        await asyncio.sleep(0.01)  # Simulated execution
        duration = round(time.monotonic() - start, 3)

        return SandboxExecutionResult(
            exit_code=0,
            stdout=f"[sandbox:{sandbox_id}] Executed: {cmd_str}",
            stderr="",
            duration_seconds=duration,
            peak_memory_mb=12.5,
        )

    async def destroy(self, sandbox_id: str) -> bool:
        async with self._lock:
            if sandbox_id in self.sandboxes:
                del self.sandboxes[sandbox_id]
                logger.info("mock_sandbox_destroyed", sandbox_id=sandbox_id)
                return True
            return False


class SandboxManager:
    """Manages active sandbox lifecycles and default execution policies."""

    def __init__(self, backend: Sandbox | None = None, default_policy: SandboxPolicy | None = None):
        self.backend = backend or MockSandbox()
        self.default_policy = default_policy or SandboxPolicy()
        self._active_sandboxes: set[str] = set()
        self._lock = asyncio.Lock()

    async def create_sandbox(self, policy: SandboxPolicy | None = None) -> str:
        """Create new isolated sandbox instance."""
        p = policy or self.default_policy
        sandbox_id = await self.backend.create(p)
        async with self._lock:
            self._active_sandboxes.add(sandbox_id)
        return sandbox_id

    async def execute_in_sandbox(
        self,
        sandbox_id: str,
        command: str | list[str],
        timeout: float | None = None,
    ) -> SandboxExecutionResult:
        """Execute command in sandbox."""
        return await self.backend.execute(sandbox_id, command, timeout=timeout)

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy sandbox."""
        async with self._lock:
            self._active_sandboxes.discard(sandbox_id)
        return await self.backend.destroy(sandbox_id)

    @property
    def active_count(self) -> int:
        return len(self._active_sandboxes)
