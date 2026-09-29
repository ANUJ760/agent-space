"""Tests for M46 — Resource Limits & Denial-of-Service Defenses.

Validates:
- Massive output stream truncation (prevents buffer and memory exhaustion)
- Fork bomb defense via strict PID limits
- Memory exhaustion defense
- Disk exhaustion defense
"""

import pytest
from packages.sandbox import (
    ResourceGovernor,
    ResourceLimitExceededError,
    ResourceLimits,
)


class TestResourceLimits:
    def test_output_stream_truncation(self) -> None:
        limits = ResourceLimits(max_output_bytes=500)
        governor = ResourceGovernor(limits)

        # 1. Normal output under limit remains intact
        normal = "Hello, world!"
        res1, truncated1 = governor.truncate_output(normal)
        assert res1 == normal
        assert truncated1 is False

        # 2. Huge output (2000 chars) truncated to 500 bytes with notice
        huge = "A" * 2000
        res2, truncated2 = governor.truncate_output(huge)
        assert truncated2 is True
        assert len(res2) < 2000
        assert "Output truncated: exceeded 500 bytes limit" in res2

    def test_fork_bomb_prevention(self) -> None:
        limits = ResourceLimits(max_pids=50)
        governor = ResourceGovernor(limits)

        # Safe process count passes
        governor.check_pids(15)

        # Hitting PID ceiling triggers defense
        with pytest.raises(ResourceLimitExceededError, match="fork bomb blocked"):
            governor.check_pids(50)

        with pytest.raises(ResourceLimitExceededError, match="fork bomb blocked"):
            governor.check_pids(120)

    def test_memory_exhaustion_defense(self) -> None:
        limits = ResourceLimits(max_memory_mb=1024)
        governor = ResourceGovernor(limits)

        # Within bounds passes
        governor.check_memory(512.0)

        # Exceeding RAM limit triggers defense
        with pytest.raises(ResourceLimitExceededError, match="Memory limit exceeded"):
            governor.check_memory(1500.0)

    def test_disk_exhaustion_defense(self) -> None:
        limits = ResourceLimits(max_disk_mb=2048)
        governor = ResourceGovernor(limits)

        # Within bounds passes
        governor.check_disk(100.0)

        # Exceeding disk quota triggers defense
        with pytest.raises(ResourceLimitExceededError, match="Disk limit exceeded"):
            governor.check_disk(3000.0)
