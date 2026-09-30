"""Tests for M82 — Kubernetes Base Manifests.

Validates the complete set of required Kubernetes base manifests per Section 91:
1. Namespace: Dedicated agent-space namespace with standard labels.
2. Deployments: Backend, Worker, and Frontend deployments configured.
3. Services: ClusterIP services for backend (8000) and frontend (3000).
4. Config: Centralized ConfigMap for environment and service discovery.
5. Secrets references: Managed secret declarations avoiding hardcoded credentials.
6. Ingress: Ingress controller routing API, WebSockets, and frontend SPA traffic.
7. Probes: Startup, liveness, and readiness probes on containers.
8. Resources: Strict CPU and memory requests and limits on every container.
"""

from pathlib import Path

import pytest
import yaml

BASE_DIR = Path(__file__).parent.parent / "deploy" / "kubernetes" / "base"


@pytest.fixture()
def namespace_manifest() -> dict:
    with open(BASE_DIR / "namespace.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def configmap_manifest() -> dict:
    with open(BASE_DIR / "configmap.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def secrets_manifest() -> dict:
    with open(BASE_DIR / "secrets.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def backend_deployment() -> dict:
    with open(BASE_DIR / "backend-deployment.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def worker_deployment() -> dict:
    with open(BASE_DIR / "worker-deployment.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def frontend_deployment() -> dict:
    with open(BASE_DIR / "frontend-deployment.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def backend_service() -> dict:
    with open(BASE_DIR / "backend-service.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def frontend_service() -> dict:
    with open(BASE_DIR / "frontend-service.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def ingress_manifest() -> dict:
    with open(BASE_DIR / "ingress.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def kustomization_manifest() -> dict:
    with open(BASE_DIR / "kustomization.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestM82KubernetesBase:
    """Verifies baseline Kubernetes resource specifications."""

    # 1. Namespace
    def test_namespace_configuration(self, namespace_manifest: dict) -> None:
        assert namespace_manifest["kind"] == "Namespace"
        assert namespace_manifest["metadata"]["name"] == "agent-space"

    # 2. Deployments
    def test_deployments_defined(
        self, backend_deployment: dict, worker_deployment: dict, frontend_deployment: dict
    ) -> None:
        deployments = [backend_deployment, worker_deployment, frontend_deployment]
        for dep in deployments:
            assert dep["kind"] == "Deployment"
            assert dep["metadata"]["namespace"] == "agent-space"
            assert dep["spec"]["replicas"] >= 2
            assert len(dep["spec"]["template"]["spec"]["containers"]) >= 1

    # 3. Services
    def test_services_routing_and_ports(
        self, backend_service: dict, frontend_service: dict
    ) -> None:
        assert backend_service["kind"] == "Service"
        assert backend_service["metadata"]["name"] == "agent-space-backend"
        assert any(p["port"] == 8000 for p in backend_service["spec"]["ports"])

        assert frontend_service["kind"] == "Service"
        assert frontend_service["metadata"]["name"] == "agent-space-frontend"
        assert any(p["port"] == 3000 for p in frontend_service["spec"]["ports"])

    # 4. Config
    def test_configmap_entries(self, configmap_manifest: dict) -> None:
        assert configmap_manifest["kind"] == "ConfigMap"
        data = configmap_manifest["data"]
        assert data["APP_ENV"] == "production"
        assert "REDIS_URL" in data
        assert "NATS_URL" in data
        assert "TEMPORAL_HOST" in data

    # 5. Secrets References
    def test_secrets_references(self, secrets_manifest: dict) -> None:
        assert secrets_manifest["kind"] == "Secret"
        assert secrets_manifest["metadata"]["name"] == "agent-space-secrets"
        keys = secrets_manifest["stringData"].keys()
        assert "DATABASE_URL" in keys
        assert "KEYCLOAK_CLIENT_SECRET" in keys
        assert "REDIS_PASSWORD" in keys

    # 6. Ingress
    def test_ingress_routing_and_tls(self, ingress_manifest: dict) -> None:
        assert ingress_manifest["kind"] == "Ingress"
        rules = ingress_manifest["spec"]["rules"]
        paths = rules[0]["http"]["paths"]

        path_map = {p["path"]: p["backend"]["service"]["name"] for p in paths}
        assert path_map["/api"] == "agent-space-backend"
        assert path_map["/ws"] == "agent-space-backend"
        assert path_map["/"] == "agent-space-frontend"
        assert "tls" in ingress_manifest["spec"]

    # 7. Probes
    def test_probes_configured_on_workloads(
        self, backend_deployment: dict, worker_deployment: dict, frontend_deployment: dict
    ) -> None:
        # Backend probes
        backend_container = backend_deployment["spec"]["template"]["spec"]["containers"][0]
        assert "startupProbe" in backend_container
        assert "livenessProbe" in backend_container
        assert "readinessProbe" in backend_container
        assert backend_container["livenessProbe"]["httpGet"]["path"] == "/health"

        # Worker probe
        worker_container = worker_deployment["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in worker_container

        # Frontend probes
        frontend_container = frontend_deployment["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in frontend_container
        assert "readinessProbe" in frontend_container

    # 8. Resources
    def test_resource_requests_and_limits_enforced(
        self, backend_deployment: dict, worker_deployment: dict, frontend_deployment: dict
    ) -> None:
        for dep in [backend_deployment, worker_deployment, frontend_deployment]:
            container = dep["spec"]["template"]["spec"]["containers"][0]
            assert "resources" in container
            res = container["resources"]
            assert "requests" in res and "cpu" in res["requests"] and "memory" in res["requests"]
            assert "limits" in res and "cpu" in res["limits"] and "memory" in res["limits"]

    # 9. Kustomization
    def test_kustomization_completeness(self, kustomization_manifest: dict) -> None:
        resources = kustomization_manifest["resources"]
        expected = [
            "namespace.yaml",
            "configmap.yaml",
            "secrets.yaml",
            "backend-deployment.yaml",
            "backend-service.yaml",
            "worker-deployment.yaml",
            "frontend-deployment.yaml",
            "frontend-service.yaml",
            "ingress.yaml",
        ]
        for exp in expected:
            assert exp in resources, f"Resource {exp} missing from kustomization.yaml"
