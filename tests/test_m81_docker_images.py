"""Tests for M81 — Production Docker Images.

Validates all 6 core hardening requirements per Section 90:
1. Non-root: All production runtime images execute as unprivileged users (e.g. UID 10001).
2. Minimal: Base images utilize slim/alpine distributions without unnecessary build tooling.
3. Pinned dependencies: Dependency versions are strictly pinned (requirements-prod.txt & package-lock.json).
4. Health checks: Native HEALTHCHECK instructions are configured for active container liveness probes.
5. No secrets: No credential baking, API keys, or .env files in Dockerfiles or build contexts.
6. Multi-stage frontend build: Distinct stages for dependencies, compilation, and isolated production runtime.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


class TestM81DockerHardening:
    """Verifies Dockerfile architecture against enterprise production specifications."""

    @pytest.fixture()
    def backend_dockerfile(self) -> str:
        path = REPO_ROOT / "docker" / "Dockerfile.backend"
        assert path.exists(), f"Backend Dockerfile not found at {path}"
        return path.read_text(encoding="utf-8")

    @pytest.fixture()
    def worker_dockerfile(self) -> str:
        path = REPO_ROOT / "docker" / "Dockerfile.worker"
        assert path.exists(), f"Worker Dockerfile not found at {path}"
        return path.read_text(encoding="utf-8")

    @pytest.fixture()
    def frontend_dockerfile(self) -> str:
        path = REPO_ROOT / "docker" / "Dockerfile.frontend"
        assert path.exists(), f"Frontend Dockerfile not found at {path}"
        return path.read_text(encoding="utf-8")

    @pytest.fixture()
    def dockerignore(self) -> str:
        path = REPO_ROOT / ".dockerignore"
        assert path.exists(), f".dockerignore not found at {path}"
        return path.read_text(encoding="utf-8")

    @pytest.fixture()
    def pinned_requirements(self) -> str:
        path = REPO_ROOT / "requirements-prod.txt"
        assert path.exists(), f"requirements-prod.txt not found at {path}"
        return path.read_text(encoding="utf-8")

    # ─── 1. Non-Root Execution ───────────────────────────────────────────────

    def test_backend_runs_as_non_root(self, backend_dockerfile: str) -> None:
        assert re.search(r"USER\s+(10001:10001|appuser)", backend_dockerfile)
        assert "groupadd" in backend_dockerfile
        assert "useradd" in backend_dockerfile

    def test_worker_runs_as_non_root(self, worker_dockerfile: str) -> None:
        assert re.search(r"USER\s+(10001:10001|appuser)", worker_dockerfile)
        assert "groupadd" in worker_dockerfile
        assert "useradd" in worker_dockerfile

    def test_frontend_runs_as_non_root(self, frontend_dockerfile: str) -> None:
        assert re.search(r"USER\s+(10001|nextjs)", frontend_dockerfile)
        assert "addgroup" in frontend_dockerfile
        assert "adduser" in frontend_dockerfile

    # ─── 2. Minimal Base Images ──────────────────────────────────────────────

    def test_minimal_base_images(
        self, backend_dockerfile: str, worker_dockerfile: str, frontend_dockerfile: str
    ) -> None:
        # Backend and Worker use slim
        assert "python:3.11-slim" in backend_dockerfile
        assert "python:3.11-slim" in worker_dockerfile

        # Frontend uses alpine
        assert "node:20-alpine" in frontend_dockerfile

    # ─── 3. Pinned Dependencies ──────────────────────────────────────────────

    def test_pinned_backend_dependencies(self, pinned_requirements: str) -> None:
        lines = [
            line.strip()
            for line in pinned_requirements.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert len(lines) >= 15
        for line in lines:
            # Ensure every dependency specification uses exact pinning (==)
            assert "==" in line, f"Dependency {line} is not strictly pinned with '=='"

    def test_frontend_uses_pinned_ci(self, frontend_dockerfile: str) -> None:
        assert "npm ci" in frontend_dockerfile

    # ─── 4. Health Checks ───────────────────────────────────────────────────

    def test_healthchecks_configured_on_all_services(
        self, backend_dockerfile: str, worker_dockerfile: str, frontend_dockerfile: str
    ) -> None:
        assert "HEALTHCHECK" in backend_dockerfile
        assert "HEALTHCHECK" in worker_dockerfile
        assert "HEALTHCHECK" in frontend_dockerfile

        # Backend healthcheck uses non-external urllib probe
        assert "http://localhost:8000/health" in backend_dockerfile

        # Frontend healthcheck verifies localhost port 3000
        assert "http://localhost:3000" in frontend_dockerfile

    # ─── 5. No Secrets Baked In ──────────────────────────────────────────────

    def test_no_secrets_in_dockerfiles(
        self, backend_dockerfile: str, worker_dockerfile: str, frontend_dockerfile: str
    ) -> None:
        combined = f"{backend_dockerfile}\n{worker_dockerfile}\n{frontend_dockerfile}"

        # No secret assignment patterns
        forbidden_patterns = [
            r"ENV\s+.*PASSWORD\s*=",
            r"ENV\s+.*SECRET\s*=",
            r"ENV\s+.*KEY\s*=",
            r"ENV\s+.*TOKEN\s*=",
            r"COPY\s+.*\.env",
            r"ADD\s+.*\.env",
        ]
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, combined, flags=re.IGNORECASE)
            assert not matches, f"Secret pattern matched in Dockerfile: {matches}"

    def test_dockerignore_excludes_credentials(self, dockerignore: str) -> None:
        patterns = [line.strip() for line in dockerignore.splitlines() if line.strip()]
        assert any(".env" in p for p in patterns)
        assert any(".git" in p for p in patterns)
        assert any("node_modules" in p for p in patterns)
        assert any("__pycache__" in p or "*.pyc" in p for p in patterns)

    # ─── 6. Multi-Stage Frontend Build ───────────────────────────────────────

    def test_frontend_multi_stage_pipeline(self, frontend_dockerfile: str) -> None:
        stages = re.findall(r"FROM\s+\S+\s+AS\s+(\w+)", frontend_dockerfile, flags=re.IGNORECASE)
        stage_names = [s.lower() for s in stages]

        assert "deps" in stage_names
        assert "builder" in stage_names
        assert "runner" in stage_names
        assert len(stage_names) == 3
