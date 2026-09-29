"""Adversarial Security Audit for Agent Space Sandboxes (M66).

Validates defenses against:
1. Docker socket access & mount abuse
2. Host filesystem access & path traversal
3. Privileged escalation attempts
4. Network escape & SSRF (loopback, RFC1918, metadata, internal services)
5. Resource exhaustion (RAM, Disk, Output buffer)
6. Fork bomb prevention (PID limits)
7. Secret discovery & credential exfiltration
8. Container breakout primitives (nsenter, chroot, /dev/mem)
"""

import pytest

from packages.sandbox.docker import DockerSandbox, DockerSecurityViolationError
from packages.sandbox.network import (
    NetworkEgressBlockedError,
    validate_egress_target,
)
from packages.sandbox.policy import SandboxPolicy
from packages.sandbox.resources import (
    ResourceGovernor,
    ResourceLimitExceededError,
    ResourceLimits,
)
from packages.security.secrets import SecretMasker


class TestSandboxSecurityAudit:
    """Comprehensive adversarial test suite auditing sandbox defenses."""

    # 1. Docker Socket Access
    def test_docker_socket_mount_blocked(self) -> None:
        sandbox = DockerSandbox()
        for sock in ["/var/run/docker.sock", "/run/docker.sock", "/var/run/../var/run/docker.sock"]:
            with pytest.raises(DockerSecurityViolationError, match="strictly forbidden"):
                sandbox.validate_mount(sock, "/tmp/sock")

    async def test_docker_socket_command_execution_blocked(self) -> None:
        sandbox = DockerSandbox()
        policy = SandboxPolicy()
        sbx_id = await sandbox.create(policy)

        result = await sandbox.execute(sbx_id, "curl --unix-socket /var/run/docker.sock http://localhost/images/json")
        assert result.exit_code == 126
        assert result.killed is True
        assert "forbidden pattern 'docker.sock'" in result.stderr

        await sandbox.destroy(sbx_id)

    # 2. Host Filesystem Access & Path Traversal
    def test_host_filesystem_mounts_blocked(self) -> None:
        sandbox = DockerSandbox()
        forbidden_targets = [
            "/",
            "/etc",
            "/etc/shadow",
            "/proc",
            "/sys",
            "/root",
            "/var",
            "/var/tmp/../../etc",
            "/tmp/../../",
        ]
        for path in forbidden_targets:
            with pytest.raises(DockerSecurityViolationError, match="strictly forbidden"):
                sandbox.validate_mount(path, "/mnt/host")

    # 3. Privileged Escalation
    def test_privilege_escalation_invariants(self) -> None:
        # Cannot be privileged
        with pytest.raises(ValueError, match="Privileged mode is strictly forbidden"):
            p1 = SandboxPolicy(privileged=True)
            p1.validate()

        # Cannot be root UID 0
        with pytest.raises(ValueError, match="Root execution is strictly forbidden"):
            p2 = SandboxPolicy(run_as_uid=0)
            p2.validate()

        # Cannot be root user string
        with pytest.raises(ValueError, match="Root execution is strictly forbidden"):
            p3 = SandboxPolicy(user="root")
            p3.validate()

    def test_container_hardened_security_opts(self) -> None:
        sandbox = DockerSandbox()
        policy = SandboxPolicy()
        config = sandbox.build_container_config(policy)

        assert config["privileged"] is False
        assert config["user"] == "10001:10001"
        assert config["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in config["security_opt"]
        assert config["read_only"] is True

    # 4. Network Escape & SSRF
    def test_network_isolation_and_ssrf_blocked(self) -> None:
        # Loopback
        for host in ["http://127.0.0.1:8080", "http://127.0.0.10:3000", "http://localhost:5432"]:
            with pytest.raises(NetworkEgressBlockedError):
                validate_egress_target(host)

        # RFC1918 Private IPv4
        for private_ip in [
            "http://10.0.0.1",
            "http://10.244.0.15:8080",
            "http://172.16.0.1",
            "http://172.20.10.4:9000",
            "http://192.168.1.1:80",
            "http://192.168.0.254:443",
        ]:
            with pytest.raises(NetworkEgressBlockedError):
                validate_egress_target(private_ip)

        # Cloud Metadata Endpoints
        for metadata in [
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://metadata/identity",
        ]:
            with pytest.raises(NetworkEgressBlockedError):
                validate_egress_target(metadata)

        # Internal Architecture Services
        for service in [
            "http://postgres:5432",
            "http://redis:6379",
            "http://nats:4222",
            "http://temporal:7233",
            "http://keycloak:8080",
            "http://gitea:3000",
        ]:
            with pytest.raises(NetworkEgressBlockedError):
                validate_egress_target(service)

    # 5. Resource Exhaustion
    def test_resource_exhaustion_limits(self) -> None:
        governor = ResourceGovernor(ResourceLimits(max_memory_mb=512, max_disk_mb=1024, max_output_bytes=500))

        # Memory limit exceeded
        with pytest.raises(ResourceLimitExceededError, match="Memory limit exceeded"):
            governor.check_memory(513.0)

        # Disk limit exceeded
        with pytest.raises(ResourceLimitExceededError, match="Disk limit exceeded"):
            governor.check_disk(1025.0)

        # Massive output stream truncated
        massive_output = "A" * 2000
        truncated, was_truncated = governor.truncate_output(massive_output)
        assert was_truncated is True
        assert len(truncated) < 600
        assert "Output truncated" in truncated

    # 6. Fork Bomb Defense
    def test_fork_bomb_pids_limit(self) -> None:
        governor = ResourceGovernor(ResourceLimits(max_pids=50))
        # Normal process count within limits
        governor.check_pids(30)

        # Fork bomb burst exceeding PID limit
        with pytest.raises(ResourceLimitExceededError, match="fork bomb blocked"):
            governor.check_pids(50)

    # 7. Secret Discovery & Masking
    def test_secret_scrubbing_in_sandbox_outputs(self) -> None:
        masker = SecretMasker()
        masker.register_secret("db_prod_master_secret_2026")

        # Even if a command attempts to echo or inspect an environment secret
        raw_output = "CONTAINER_ENV: DB_PASS=db_prod_master_secret_2026 and AWS=AKIAIOSFODNN7EXAMPLE"
        scrubbed = masker.mask_text(raw_output)

        assert "db_prod_master_secret_2026" not in scrubbed
        assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
        assert "***MASKED***" in scrubbed

    # 8. Container Breakout Primitives
    @pytest.mark.asyncio
    async def test_container_breakout_primitives_blocked(self) -> None:
        sandbox = DockerSandbox()
        policy = SandboxPolicy()
        sbx_id = await sandbox.create(policy)

        breakout_attacks = [
            "nsenter -t 1 -m -u -i -n -p sh",
            "chroot /hostfs /bin/bash",
            "dd if=/dev/mem bs=1k count=1",
            "dd if=/dev/kmem bs=1k count=1",
            "mkfs.ext4 /dev/sda",
        ]

        for attack in breakout_attacks:
            res = await sandbox.execute(sbx_id, attack)
            assert res.exit_code == 126
            assert res.killed is True
            assert "Security violation" in res.stderr

        await sandbox.destroy(sbx_id)
