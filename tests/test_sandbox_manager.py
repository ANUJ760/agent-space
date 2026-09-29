"""Tests for M43 — Sandbox Manager.

Validates:
- SandboxPolicy enforcement: non-root, unprivileged, resource limit validation
- SandboxManager lifecycle: create, execute, destroy
- Rejection of root/privileged execution attempts
- Resource constraints tracking
"""

import pytest

from packages.sandbox import NetworkPolicy, SandboxManager, SandboxPolicy


class TestSandboxManager:
    def test_privileged_policy_rejected(self) -> None:
        policy = SandboxPolicy(privileged=True)
        with pytest.raises(ValueError, match="Privileged mode is strictly forbidden"):
            policy.validate()

    def test_root_user_policy_rejected(self) -> None:
        policy = SandboxPolicy(user="root", run_as_uid=0)
        with pytest.raises(ValueError, match="Root execution is strictly forbidden"):
            policy.validate()

    def test_default_policy_invariants(self) -> None:
        policy = SandboxPolicy()
        policy.validate()  # Must not raise
        assert policy.network == NetworkPolicy.DENY
        assert policy.user == "sandboxuser"
        assert policy.run_as_uid == 10001
        assert policy.privileged is False
        assert "ALL" in policy.capabilities_drop
        assert policy.read_only_rootfs is True

    async def test_sandbox_lifecycle(self) -> None:
        manager = SandboxManager()
        assert manager.active_count == 0

        # 1. Create
        sbx_id = await manager.create_sandbox()
        assert sbx_id.startswith("sbx-")
        assert manager.active_count == 1

        # 2. Execute command
        res = await manager.execute_in_sandbox(sbx_id, "pytest tests/")
        assert res.exit_code == 0
        assert "pytest tests/" in res.stdout
        assert res.duration_seconds >= 0.0

        # 3. Destroy
        destroyed = await manager.destroy_sandbox(sbx_id)
        assert destroyed is True
        assert manager.active_count == 0

    async def test_escalation_attempt_blocked_in_sandbox(self) -> None:
        manager = SandboxManager()
        sbx_id = await manager.create_sandbox()

        res = await manager.execute_in_sandbox(sbx_id, "sudo apt-get install malware")
        assert res.exit_code != 0
        assert "Root privilege escalation is strictly forbidden" in res.stderr
        await manager.destroy_sandbox(sbx_id)
