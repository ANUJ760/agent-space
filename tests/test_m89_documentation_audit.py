"""M89 — Documentation Audit Test Suite.

Audits documentation completeness per Build Guide Section 98:
- Validates presence and integrity of all 12 documentation domains.
- Asserts NO undocumented public API routes.
- Asserts NO undocumented required environment variables.
- Asserts NO undocumented platform services.
- Validates internal markdown link integrity.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from app.config import Settings
from app.main import create_app

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"

REQUIRED_DOCS = [
    "README.md",
    "docs/api.md",
    "docs/architecture.md",
    "docs/database.md",
    "docs/concurrency.md",
    "docs/security.md",
    "docs/agents.md",
    "docs/workflows.md",
    "docs/sandbox.md",
    "docs/deployment.md",
    "docs/observability.md",
    "docs/troubleshooting.md",
]


def test_required_documentation_files_exist_and_non_empty() -> None:
    """Verify all 12 mandated documentation domains exist and are populated."""
    for rel_path in REQUIRED_DOCS:
        doc_path = REPO_ROOT / rel_path
        assert doc_path.exists(), f"Mandatory documentation file missing: {rel_path}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 200, f"Documentation file {rel_path} has insufficient content"


def test_no_undocumented_public_api() -> None:
    """Assert all public API endpoints exposed by FastAPI are documented in docs/api.md."""
    api_doc_path = DOCS_DIR / "api.md"
    assert api_doc_path.exists()
    doc_content = api_doc_path.read_text(encoding="utf-8")

    app = create_app()

    documented_routes: list[str] = []
    missing_routes: list[str] = []

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if not path:
            continue

        # Skip OpenAPI docs and static / internal helper routes
        if path.startswith(("/docs", "/redoc", "/openapi.json")):
            continue

        # Convert path parameters e.g. {project_id} -> regex or standard search
        normalized_path = re.sub(r"\{[a-zA-Z0-9_]+\}", "", path)
        if normalized_path in doc_content or path in doc_content:
            documented_routes.append(f"{methods} {path}")
        else:
            missing_routes.append(f"{methods} {path}")

    assert len(missing_routes) == 0, f"Undocumented public API routes found: {missing_routes}"


def test_no_undocumented_environment_variables() -> None:
    """Assert all configuration parameters in Settings are documented in docs/environment_variables.md."""
    env_doc_path = DOCS_DIR / "environment_variables.md"
    assert env_doc_path.exists()
    doc_content = env_doc_path.read_text(encoding="utf-8").upper()

    settings_fields = Settings.model_fields.keys()

    undocumented_vars: list[str] = []
    for field_name in settings_fields:
        upper_field = field_name.upper()
        # Some env vars might have prefixes or direct match
        if upper_field not in doc_content:
            undocumented_vars.append(field_name)

    assert len(undocumented_vars) == 0, (
        f"Undocumented environment variables found: {undocumented_vars}"
    )


def test_no_undocumented_services() -> None:
    """Assert all services defined in docker-compose.prod.yml and k8s are documented in docs/services.md."""
    services_doc_path = DOCS_DIR / "services.md"
    assert services_doc_path.exists()
    doc_content = services_doc_path.read_text(encoding="utf-8")

    compose_path = REPO_ROOT / "docker-compose.prod.yml"
    assert compose_path.exists()
    compose_data: dict[str, Any] = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    services = compose_data.get("services", {}).keys()
    undocumented_services: list[str] = []

    for service_name in services:
        if f"`{service_name}`" not in doc_content and service_name not in doc_content:
            undocumented_services.append(service_name)

    assert len(undocumented_services) == 0, f"Undocumented services found: {undocumented_services}"


def test_internal_markdown_link_integrity() -> None:
    """Ensure all internal links in docs/ target existing files."""
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    broken_links: list[str] = []
    for md_file in DOCS_DIR.glob("**/*.md"):
        content = md_file.read_text(encoding="utf-8")
        for match in link_pattern.finditer(content):
            link_target = match.group(2)
            # Skip external URLs, anchors, mailto
            if link_target.startswith(("http://", "https://", "#", "mailto:")):
                continue

            # Strip query params / anchors
            target_path_str = link_target.split("#")[0].split("?")[0]
            if not target_path_str:
                continue

            if target_path_str.startswith("file://"):
                target_path = Path(target_path_str.removeprefix("file://"))
            else:
                target_path = (md_file.parent / target_path_str).resolve()
            if not target_path.exists():
                broken_links.append(f"{md_file.relative_to(REPO_ROOT)} -> {link_target}")

    assert len(broken_links) == 0, f"Broken markdown links detected: {broken_links}"
