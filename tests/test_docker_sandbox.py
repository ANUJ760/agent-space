"""Tests for M44 — Docker Execution & Sandboxing Security.

Validates:
- Hardened Docker container configuration (non-root, unprivileged, readonly rootfs, no-new-privileges)
- Strict prohibition of Docker socket mounts (/var/run/docker.sock)
- Prevention of malicious container escape attempts (nsenter, chroot, /dev/mem)
- Clean lifecycle and execution under timeout
"""

import pytest

from packages.sandbox import (
    DockerSandbox,
    DockerSecurityViolationError,
    NetworkPolicy,
    SandboxPolicy,
)


class TestDockerSandbox:
    def test_container_config_security_hardening(self) -> None:
        sandbox = DockerSandbox()
        policy = SandboxPolicy(
            cpu_limit=1.5,
            ram_limit_mb=512,
            pids_limit=50,
            network=NetworkPolicy.DENY,
        )
        config = sandbox.build_container_config(policy)

        # Mandatory security checks
        assert config["user"] == "10001:10001"  # Non-root
        assert config["privileged"] is False  # Never privileged
        assert config["cap_drop"] == ["ALL"]  # All capabilities dropped
        assert "no-new-privileges:true" in config["security_opt"]
        assert config["network_disabled"] is True
        assert config["read_only"] is True
        assert config["pids_limit"] == 50
        assert config["mem_limit"] == "512m"
        assert config["nano_cpus"] == 1500000000

    def test_forbidden_mount_rejected(self) -> None:
        sandbox = DockerSandbox()

        # Attempt to mount Docker socket
        with pytest.raises(DockerSecurityViolationError, match="strictly forbidden"):
            sandbox.validate_mount("/var/run/docker.sock", "/var/run/docker.sock")

        # Attempt to mount host root
        with pytest.raises(DockerSecurityViolationError, match="strictly forbidden"):
            sandbox.validate_mount("/", "/host")

        # Attempt to mount host /etc
        with pytest.raises(DockerSecurityViolationError, match="strictly forbidden"):
            sandbox.validate_mount("/etc", "/container_etc")

    async def test_malicious_commands_blocked(self) -> None:
        sandbox = DockerSandbox()
        policy = SandboxPolicy()
        sbx_id = await sandbox.create(policy)

        # 1. nsenter escape attempt
        res1 = await sandbox.execute(sbx_id, "nsenter --target 1 --mount --uts --ipc --net --pid")
        assert res1.exit_code == 126
        assert "Security violation" in res1.stderr
        assert res1.killed is True

        # 2. chroot attempt
        res2 = await sandbox.execute(sbx_id, "chroot /host /bin/bash")
        assert res2.exit_code == 126
        assert "Security violation" in res2.stderr

        # 3. Direct memory access attempt
        res3 = await sandbox.execute(sbx_id, "cat /dev/mem")
        assert res3.exit_code == 126
        assert "Security violation" in res3.stderr

        # 4. Safe command should succeed
        res4 = await sandbox.execute(sbx_id, "python3 -m unittest discover")
        assert res4.exit_code == 0
        assert "unittest discover" in res4.stdout

        await sandbox.destroy(sbx_id)
