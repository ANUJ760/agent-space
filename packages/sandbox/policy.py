"""Sandbox security policies and resource constraints for isolated execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class NetworkPolicy(StrEnum):
    """Network egress policy for sandboxes."""

    DENY = "DENY"
    ALLOWLIST_ONLY = "ALLOWLIST_ONLY"
    UNRESTRICTED = "UNRESTRICTED"


@dataclass
class SandboxPolicy:
    """Security and resource limits enforced on all sandbox executions."""

    # Compute & Memory Limits
    cpu_limit: float = 1.0  # Max CPU cores (e.g. 1.0 = 100% of 1 core)
    ram_limit_mb: int = 1024  # Max RAM in MB
    disk_limit_mb: int = 5120  # Max disk usage in MB
    pids_limit: int = 100  # Max process count (prevents fork bombs)
    timeout_seconds: int = 300  # Default 5-minute timeout

    # Security & Isolation Constraints
    network: NetworkPolicy = NetworkPolicy.DENY  # Network DENY by default
    network_allowlist: list[str] = field(default_factory=list)
    user: str = "sandboxuser"  # Strictly non-root (UID 10001)
    run_as_uid: int = 10001
    privileged: bool = False  # NEVER privileged
    capabilities_drop: list[str] = field(default_factory=lambda: ["ALL"])
    read_only_rootfs: bool = True  # Ephemeral read-only root
    workdir: str = "/workspace"
    ephemeral_tmp_mb: int = 256  # Size-limited tmpfs for /tmp

    def validate(self) -> None:
        """Validate policy invariants to prevent misconfigurations."""
        if self.privileged:
            raise ValueError("Privileged mode is strictly forbidden in Agent Space sandboxes")
        if self.run_as_uid == 0 or self.user == "root":
            raise ValueError("Root execution is strictly forbidden in Agent Space sandboxes")
        if self.pids_limit < 1 or self.pids_limit > 1000:
            raise ValueError("pids_limit must be between 1 and 1000")
        if self.ram_limit_mb < 64:
            raise ValueError("ram_limit_mb must be at least 64MB")
