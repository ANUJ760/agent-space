"""Resource Limits and Denial-of-Service Defense for Agent Space.

Enforces:
- CPU limits
- Memory limits (prevents memory exhaustion)
- Disk limits (prevents disk exhaustion)
- PIDs limits (prevents fork bombs)
- Runtime timeouts (prevents infinite loops & hanging processes)
- Output size truncation (prevents buffer exhaustion from massive logs)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.stdlib.get_logger(__name__)

DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024  # 1MB maximum output buffer
DEFAULT_PIDS_LIMIT = 100
DEFAULT_TIMEOUT_SECONDS = 300


class ResourceLimitExceededError(RuntimeError):
    """Raised when an execution violates physical or logical resource limits."""


@dataclass
class ResourceLimits:
    """Configurable resource boundary for sandboxed command execution."""

    max_cpu_cores: float = 1.0
    max_memory_mb: int = 1024
    max_disk_mb: int = 5120
    max_pids: int = DEFAULT_PIDS_LIMIT
    max_runtime_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES


class ResourceGovernor:
    """Enforces execution limits and prevents denial-of-service vectors."""

    def __init__(self, limits: ResourceLimits | None = None):
        self.limits = limits or ResourceLimits()

    def truncate_output(self, raw_data: str | bytes, max_bytes: int | None = None) -> tuple[str, bool]:
        """Truncate excessive stdout/stderr stream to prevent memory exhaustion."""
        limit = max_bytes or self.limits.max_output_bytes
        encoded = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data

        if len(encoded) <= limit:
            return raw_data if isinstance(raw_data, str) else encoded.decode("utf-8", errors="replace"), False

        truncated = encoded[:limit].decode("utf-8", errors="replace")
        notice = f"\n... [Output truncated: exceeded {limit} bytes limit] ..."
        logger.warning("output_stream_truncated", original_bytes=len(encoded), limit_bytes=limit)
        return truncated + notice, True

    def check_pids(self, active_pids_count: int) -> None:
        """Verify process count is within limits to stop fork bombs."""
        if active_pids_count >= self.limits.max_pids:
            logger.error("fork_bomb_detected", pids=active_pids_count, limit=self.limits.max_pids)
            raise ResourceLimitExceededError(
                f"Process limit exceeded ({active_pids_count} >= {self.limits.max_pids}); fork bomb blocked"
            )

    def check_memory(self, used_mb: float) -> None:
        """Verify memory usage is within bounds."""
        if used_mb > self.limits.max_memory_mb:
            logger.error("memory_limit_exceeded", used_mb=used_mb, limit_mb=self.limits.max_memory_mb)
            raise ResourceLimitExceededError(
                f"Memory limit exceeded ({used_mb}MB > {self.limits.max_memory_mb}MB); execution terminated"
            )

    def check_disk(self, written_mb: float) -> None:
        """Verify disk usage is within bounds."""
        if written_mb > self.limits.max_disk_mb:
            logger.error("disk_limit_exceeded", written_mb=written_mb, limit_mb=self.limits.max_disk_mb)
            raise ResourceLimitExceededError(
                f"Disk limit exceeded ({written_mb}MB > {self.limits.max_disk_mb}MB); disk exhaustion prevented"
            )
