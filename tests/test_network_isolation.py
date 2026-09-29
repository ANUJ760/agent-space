"""Tests for M45 — Network Isolation & SSRF Egress Defense.

Validates:
- Blocking of localhost and loopback targets (127.0.0.1, ::1, localhost)
- Blocking of cloud metadata endpoints (169.254.169.254, metadata.google.internal)
- Blocking of RFC1918 private network spaces (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Blocking of internal platform services (postgres, keycloak, redis, temporal, nats)
- Strict egress allowlist enforcement for approved external services
"""

import pytest

from packages.sandbox import NetworkEgressBlockedError, validate_egress_target


class TestNetworkIsolation:
    @pytest.mark.parametrize(
        "target",
        [
            "http://localhost:8000/api",
            "http://127.0.0.1:5432",
            "http://127.0.0.2:80",
            "http://app.localhost:3000",
            "http://[::1]:8080",
        ],
    )
    def test_localhost_and_loopback_blocked(self, target: str) -> None:
        with pytest.raises(NetworkEgressBlockedError, match="blocked"):
            validate_egress_target(target)

    @pytest.mark.parametrize(
        "target",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://metadata/v1/instance",
        ],
    )
    def test_cloud_metadata_endpoints_blocked(self, target: str) -> None:
        with pytest.raises(NetworkEgressBlockedError, match="blocked"):
            validate_egress_target(target)

    @pytest.mark.parametrize(
        "target",
        [
            "http://10.0.0.1/admin",
            "http://10.254.0.5:8000",
            "http://172.16.0.1:443",
            "http://172.31.255.254",
            "http://192.168.1.1/router",
            "http://192.168.0.100:8080",
        ],
    )
    def test_rfc1918_private_networks_blocked(self, target: str) -> None:
        with pytest.raises(NetworkEgressBlockedError, match="blocked"):
            validate_egress_target(target)

    @pytest.mark.parametrize(
        "target",
        [
            "http://postgres:5432",
            "http://keycloak:8080",
            "http://redis:6379",
            "http://nats:4222",
            "http://temporal:7233",
            "http://backend.internal:8000",
        ],
    )
    def test_internal_service_hostnames_blocked(self, target: str) -> None:
        with pytest.raises(NetworkEgressBlockedError, match="blocked"):
            validate_egress_target(target)

    def test_allowlist_enforcement(self) -> None:
        allowlist = ["pypi.org", "pythonhosted.org", "github.com"]

        # Exact match in allowlist succeeds
        assert validate_egress_target("https://pypi.org/simple", allowlist=allowlist) is True
        assert validate_egress_target("https://github.com/torvalds/linux", allowlist=allowlist) is True

        # Subdomain match succeeds
        assert validate_egress_target("https://files.pythonhosted.org/packages/123", allowlist=allowlist) is True
        assert validate_egress_target("https://api.github.com/repos", allowlist=allowlist) is True

        # Unapproved external domain rejected
        with pytest.raises(NetworkEgressBlockedError, match="not in sandbox network allowlist"):
            validate_egress_target("https://malicious-external-site.com", allowlist=allowlist)

        with pytest.raises(NetworkEgressBlockedError, match="not in sandbox network allowlist"):
            validate_egress_target("https://google.com", allowlist=allowlist)
