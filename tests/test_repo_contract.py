"""Tests for M00 — Repository & Engineering Contract.

Verifies repository structure, tooling configs, gitignore rules,
and environment template integrity.
"""

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_required_directories_exist() -> None:
    required_dirs = [
        "apps",
        "agents",
        "packages",
        "infrastructure",
        "docs",
        "tests",
    ]
    for directory in required_dirs:
        dir_path = REPO_ROOT / directory
        assert dir_path.is_dir(), f"Expected directory '{directory}' does not exist"


def test_required_files_exist() -> None:
    required_files = [
        "README.md",
        "LICENSE",
        ".gitignore",
        ".dockerignore",
        ".env.example",
        "Makefile",
        "pyproject.toml",
        "package.json",
        "docs/architecture.md",
        "docs/engineering-contract.md",
    ]
    for file_name in required_files:
        file_path = REPO_ROOT / file_name
        assert file_path.is_file(), f"Expected file '{file_name}' does not exist"


def test_gitignore_contains_sensitive_patterns() -> None:
    gitignore_path = REPO_ROOT / ".gitignore"
    content = gitignore_path.read_text()
    expected_patterns = [
        "__pycache__/",
        ".venv/",
        "node_modules/",
        ".env",
        "*.key",
        "*.pem",
    ]
    for pattern in expected_patterns:
        assert pattern in content, f"Expected '{pattern}' in .gitignore"


def test_dockerignore_contains_essential_patterns() -> None:
    dockerignore_path = REPO_ROOT / ".dockerignore"
    content = dockerignore_path.read_text()
    expected_patterns = [
        "**/.git",
        "**/node_modules",
        "**/.venv",
        "**/__pycache__",
    ]
    for pattern in expected_patterns:
        assert pattern in content, f"Expected '{pattern}' in .dockerignore"


def test_env_example_covers_all_subsystems() -> None:
    env_example_path = REPO_ROOT / ".env.example"
    content = env_example_path.read_text()
    required_keys = [
        "DATABASE_URL",
        "REDIS_URL",
        "NATS_URL",
        "TEMPORAL_HOST",
        "KEYCLOAK_SERVER_URL",
        "QDRANT_URL",
        "STORAGE_ENDPOINT",
        "GITEA_URL",
        "MODEL_GATEWAY_PROVIDER",
        "SANDBOX_TYPE",
        "LOG_LEVEL",
    ]
    for key in required_keys:
        assert key in content, f"Expected key '{key}' in .env.example"


def test_pyproject_toml_is_valid() -> None:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["name"] == "agent-space"
    assert "tool" in data
    assert "pytest" in data["tool"]
    assert "ruff" in data["tool"]
    assert "mypy" in data["tool"]


def test_package_json_is_valid() -> None:
    package_json_path = REPO_ROOT / "package.json"
    data = json.loads(package_json_path.read_text())
    assert data["name"] == "agent-space-workspace"
    assert "workspaces" in data
    assert "apps/*" in data["workspaces"]
    assert "packages/*" in data["workspaces"]


def test_makefile_has_standard_targets() -> None:
    makefile_path = REPO_ROOT / "Makefile"
    content = makefile_path.read_text()
    expected_targets = [
        "help:",
        "setup:",
        "test:",
        "lint:",
        "format:",
        "check:",
        "clean:",
    ]
    for target in expected_targets:
        assert target in content, f"Expected Makefile target '{target}'"
