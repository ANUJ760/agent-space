"""Tests for M83 — Kubernetes Security Hardening.

Validates all 7 enterprise Kubernetes security requirements per Section 92:
1. NetworkPolicies: Default-deny all, explicit zero-trust pod-to-pod and service microsegmentation.
2. Pod Security: Namespace restricted standard enforcement and container securityContext hardening.
3. Service Account RBAC: Dedicated unprivileged ServiceAccounts with automount disabled and scoped Role/RoleBindings.
4. Non-root: Unprivileged non-root execution (UID 10001) enforced across all pods and containers.
5. Read-only filesystems: readOnlyRootFilesystem enabled with emptyDir temporary volumes.
6. Resource limits: Strict CPU and memory requests and limits on every workload container.
7. Image policy: Pinned immutable image tags (no ':latest') and explicit pull policy.
"""

from pathlib import Path

import pytest
import yaml

BASE_DIR = Path(__file__).parent.parent / "deploy" / "kubernetes" / "base"


@pytest.fixture()
def network_policies() -> list[dict]:
    with open(BASE_DIR / "network-policies.yaml", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
        return [d for d in docs if d is not None]


@pytest.fixture()
def rbac_manifests() -> list[dict]:
    with open(BASE_DIR / "rbac.yaml", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
        return [d for d in docs if d is not None]


@pytest.fixture()
def namespace_manifest() -> dict:
    with open(BASE_DIR / "namespace.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def all_deployments() -> list[dict]:
    deployments = []
    for filename in [
        "backend-deployment.yaml",
        "worker-deployment.yaml",
        "frontend-deployment.yaml",
    ]:
        with open(BASE_DIR / filename, encoding="utf-8") as f:
            deployments.append(yaml.safe_load(f))
    return deployments


class TestM83KubernetesSecurity:
    """Automated security audits for Kubernetes deployment manifests."""

    # ─── 1. NetworkPolicies ──────────────────────────────────────────────────

    def test_default_deny_all_configured(self, network_policies: list[dict]) -> None:
        default_deny = next(
            (p for p in network_policies if p["metadata"]["name"] == "default-deny-all"), None
        )
        assert default_deny is not None, "default-deny-all NetworkPolicy missing"
        assert default_deny["spec"]["podSelector"] == {}
        assert "Ingress" in default_deny["spec"]["policyTypes"]
        assert "Egress" in default_deny["spec"]["policyTypes"]

    def test_dns_egress_policy_present(self, network_policies: list[dict]) -> None:
        dns_policy = next(
            (p for p in network_policies if p["metadata"]["name"] == "allow-dns-egress"), None
        )
        assert dns_policy is not None, "allow-dns-egress NetworkPolicy missing"
        egress = dns_policy["spec"]["egress"]
        assert any(any(p["port"] == 53 for p in rule.get("ports", [])) for rule in egress)

    def test_microsegmentation_policies(self, network_policies: list[dict]) -> None:
        policy_names = [p["metadata"]["name"] for p in network_policies]
        assert "frontend-network-policy" in policy_names
        assert "backend-network-policy" in policy_names
        assert "worker-network-policy" in policy_names

        # Worker should have no ingress
        worker_policy = next(
            p for p in network_policies if p["metadata"]["name"] == "worker-network-policy"
        )
        assert worker_policy["spec"].get("ingress") == []

    # ─── 2. Pod Security ─────────────────────────────────────────────────────

    def test_namespace_pod_security_restricted(self, namespace_manifest: dict) -> None:
        labels = namespace_manifest["metadata"]["labels"]
        assert labels.get("pod-security.kubernetes.io/enforce") == "restricted"
        assert labels.get("pod-security.kubernetes.io/audit") == "restricted"
        assert labels.get("pod-security.kubernetes.io/warn") == "restricted"

    def test_container_security_context_hardening(self, all_deployments: list[dict]) -> None:
        for dep in all_deployments:
            pod_spec = dep["spec"]["template"]["spec"]
            assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"

            for container in pod_spec["containers"]:
                sc = container["securityContext"]
                assert sc["allowPrivilegeEscalation"] is False
                assert sc["capabilities"]["drop"] == ["ALL"]

    # ─── 3. Service Account RBAC ─────────────────────────────────────────────

    def test_dedicated_service_accounts_no_token_automount(
        self, rbac_manifests: list[dict]
    ) -> None:
        sas = [m for m in rbac_manifests if m["kind"] == "ServiceAccount"]
        sa_names = {sa["metadata"]["name"] for sa in sas}

        assert "agent-space-backend" in sa_names
        assert "agent-space-worker" in sa_names
        assert "agent-space-frontend" in sa_names

        for sa in sas:
            assert sa.get("automountServiceAccountToken") is False

    def test_deployments_reference_dedicated_service_accounts(
        self, all_deployments: list[dict]
    ) -> None:
        for dep in all_deployments:
            pod_spec = dep["spec"]["template"]["spec"]
            assert "serviceAccountName" in pod_spec
            assert pod_spec["serviceAccountName"].startswith("agent-space-")

    def test_role_permissions_least_privilege(self, rbac_manifests: list[dict]) -> None:
        roles = [m for m in rbac_manifests if m["kind"] == "Role"]
        assert len(roles) >= 1
        for role in roles:
            for rule in role["rules"]:
                # Ensure no wildcard grants
                assert "*" not in rule["verbs"]
                assert "*" not in rule["resources"]

    # ─── 4. Non-Root Execution ───────────────────────────────────────────────

    def test_non_root_execution_enforced(self, all_deployments: list[dict]) -> None:
        for dep in all_deployments:
            pod_sec = dep["spec"]["template"]["spec"]["securityContext"]
            assert pod_sec["runAsNonRoot"] is True
            assert pod_sec["runAsUser"] == 10001
            assert pod_sec["runAsGroup"] == 10001
            assert pod_sec["fsGroup"] == 10001

    # ─── 5. Read-Only Filesystems ────────────────────────────────────────────

    def test_readonly_root_filesystem_enforced(self, all_deployments: list[dict]) -> None:
        for dep in all_deployments:
            for container in dep["spec"]["template"]["spec"]["containers"]:
                assert container["securityContext"]["readOnlyRootFilesystem"] is True

            # All deployments must mount writable volumes as emptyDir
            volumes = dep["spec"]["template"]["spec"]["volumes"]
            assert any("emptyDir" in v for v in volumes)

    # ─── 6. Resource Limits ──────────────────────────────────────────────────

    def test_cpu_memory_limits_configured(self, all_deployments: list[dict]) -> None:
        for dep in all_deployments:
            for container in dep["spec"]["template"]["spec"]["containers"]:
                res = container["resources"]
                assert (
                    "requests" in res and "cpu" in res["requests"] and "memory" in res["requests"]
                )
                assert "limits" in res and "cpu" in res["limits"] and "memory" in res["limits"]

    # ─── 7. Image Policy ─────────────────────────────────────────────────────

    def test_immutable_image_tags_no_latest(self, all_deployments: list[dict]) -> None:
        for dep in all_deployments:
            for container in dep["spec"]["template"]["spec"]["containers"]:
                image = container["image"]
                assert not image.endswith(":latest"), (
                    f"Mutable ':latest' tag forbidden in image {image}"
                )
                assert ":" in image, f"Image must specify an explicit tag: {image}"
                assert container.get("imagePullPolicy") == "IfNotPresent"
