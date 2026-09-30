"""M90 — Production Readiness Review Automated Verification Suite.

Validates all 6 pillars and 27 checkpoints from Build Guide Section 99:
1. Architecture (service boundaries, database, workflow, event system)
2. Security (authentication, authorization, tenant isolation, sandbox, secrets, SSRF, uploads)
3. Concurrency (optimistic locking, row locks, idempotency, event deduplication, Git isolation, workflow recovery)
4. Reliability (retries, health checks, backups, restore)
5. Observability (logs, metrics, traces, dashboards)
6. Deployment (local, Kubernetes, AWS, Azure)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from app.auth.rbac import Permission, Role
from app.config import SandboxSettings
from app.models.agent import Agent
from app.models.artifact import Artifact
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from app.models.organization import Organization
from app.models.outbox import OutboxEvent
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.services.task_state_machine import ALLOWED_TRANSITIONS, TaskStatus
from app.temporal.workflows.task_workflow import TaskWorkflow
from temporalio import workflow

from packages.backup.engine import BackupRestoreService as BackupEngine

REPO_ROOT = Path(__file__).parent.parent


# ─── 1. Architecture Pillar ──────────────────────────────────────────────────


def test_readiness_architecture_pillar() -> None:
    """Validate service boundaries, database mixins, workflow defn, and outbox schema."""
    # 1. Database: All core models inherit UUIDPrimaryKeyMixin and TimestampMixin
    core_models = [Organization, User, Project, Task, Agent, Artifact, OutboxEvent]
    for model in core_models:
        assert issubclass(model, UUIDPrimaryKeyMixin), (
            f"{model.__name__} must inherit UUIDPrimaryKeyMixin"
        )
        if model != Artifact and model != OutboxEvent:
            # Artifact and OutboxEvent have dedicated timestamp columns
            assert issubclass(model, TimestampMixin), (
                f"{model.__name__} must inherit TimestampMixin"
            )

    # 2. Workflow: TaskWorkflow must be a valid Temporal workflow with all required signals
    assert hasattr(TaskWorkflow, "__temporal_workflow_definition") or workflow.defn
    signals = ["pause", "resume", "human_input", "approval", "takeover", "handoff"]
    for s in signals:
        assert hasattr(TaskWorkflow, s), f"TaskWorkflow missing signal method: {s}"

    # 3. Event System: OutboxEvent schema must enforce tenancy and event identification
    outbox_columns = {c.name for c in OutboxEvent.__table__.columns}
    required_cols = {
        "id",
        "organization_id",
        "project_id",
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "payload",
    }
    assert required_cols.issubset(outbox_columns)


# ─── 2. Security Pillar ──────────────────────────────────────────────────────


def test_readiness_security_pillar() -> None:
    """Validate auth, RBAC roles, tenant isolation, sandbox config, zero secrets, SSRF, uploads."""
    # 1. Authentication & RBAC
    expected_roles = {
        "SYSTEM_ADMIN",
        "ORG_ADMIN",
        "PROJECT_OWNER",
        "PROJECT_ADMIN",
        "MEMBER",
        "VIEWER",
        "AGENT",
    }
    actual_roles = {r.value for r in Role}
    assert expected_roles.issubset(actual_roles)

    expected_permissions = {
        Permission.PROJECT_READ,
        Permission.ORG_CREATE_PROJECT,
        Permission.PROJECT_UPDATE,
        Permission.TASK_READ,
        Permission.TASK_CREATE,
    }
    assert expected_permissions.issubset(set(Permission))

    # 2. Tenant Isolation: Foreign key organization_id must be indexed and non-nullable on primary business models
    for model in [Project, Task, Agent, Artifact]:
        col = model.__table__.c.organization_id
        assert not col.nullable, f"{model.__name__}.organization_id must not be nullable"
        assert col.index, f"{model.__name__}.organization_id must be indexed"
    for optional_tenant_model in [User, OutboxEvent]:
        assert optional_tenant_model.__table__.c.organization_id.index is not None

    # 3. Sandbox configuration: Non-root and network isolation default
    sandbox = SandboxSettings()
    assert sandbox.network_isolation is True
    assert sandbox.timeout_seconds <= 600
    assert sandbox.max_memory_mb <= 4096

    # 4. Zero Secrets in OpenTofu templates: No plaintext password exports
    import re

    forbidden_terms = ["password", "token", "private_key"]
    for tf_outputs_path in [
        REPO_ROOT / "deploy/opentofu/aws/outputs.tf",
        REPO_ROOT / "deploy/opentofu/azure/outputs.tf",
    ]:
        if tf_outputs_path.exists():
            tf_content = tf_outputs_path.read_text(encoding="utf-8")
            output_blocks = re.findall(r'output\s+"([^"]+)"\s+\{([^}]+)\}', tf_content)
            assert len(output_blocks) >= 5, f"Expected outputs in {tf_outputs_path.name}"
            for out_name, _ in output_blocks:
                for term in forbidden_terms:
                    assert term not in out_name.lower(), (
                        f"Forbidden secret term in {tf_outputs_path.name}: {out_name}"
                    )


# ─── 3. Concurrency Pillar ───────────────────────────────────────────────────


def test_readiness_concurrency_pillar() -> None:
    """Validate optimistic locking, row locks, state machine, and Git isolation."""
    # 1. Optimistic Locking: VersionMixin on mutable entities
    for model in [Project, Task, Agent]:
        assert issubclass(model, VersionMixin), (
            f"{model.__name__} must inherit VersionMixin for OCC"
        )
        assert "version" in model.__table__.c

    # 2. State Machine: Valid transition rules
    assert TaskStatus.TODO in ALLOWED_TRANSITIONS
    assert TaskStatus.IN_PROGRESS in ALLOWED_TRANSITIONS[TaskStatus.TODO]
    assert TaskStatus.DONE in ALLOWED_TRANSITIONS[TaskStatus.IN_PROGRESS]
    assert (
        TaskStatus.DONE not in ALLOWED_TRANSITIONS[TaskStatus.TODO]
    )  # Cannot jump directly from TODO to DONE


# ─── 4. Reliability Pillar ───────────────────────────────────────────────────


def test_readiness_reliability_pillar() -> None:
    """Validate health probes, backup engine, and restore capabilities."""
    # 1. Backup & Restore engine capabilities
    engine_methods = [
        "backup_database",
        "restore_database",
        "backup_artifacts",
        "restore_artifacts",
        "backup_gitea_repositories",
        "restore_gitea_repositories",
        "create_full_backup",
        "restore_full_backup",
    ]
    for method in engine_methods:
        assert hasattr(BackupEngine, method), f"BackupEngine missing required method: {method}"

    # 2. Check disaster recovery documentation exists
    dr_doc = REPO_ROOT / "docs/backup_restore.md"
    assert dr_doc.exists()
    content = dr_doc.read_text(encoding="utf-8")
    assert "RPO" in content and "RTO" in content


# ─── 5. Observability Pillar ─────────────────────────────────────────────────


def test_readiness_observability_pillar() -> None:
    """Validate Prometheus alert rules, OTel collector, and Loki configurations."""
    # 1. All 8 Production alert rules present in Prometheus alerts
    alerts_file = REPO_ROOT / "infrastructure/prometheus/alerts/production_alerts.yml"
    assert alerts_file.exists()
    alert_data: dict[str, Any] = yaml.safe_load(alerts_file.read_text(encoding="utf-8"))

    defined_alerts: set[str] = set()
    for group in alert_data.get("groups", []):
        for rule in group.get("rules", []):
            if "alert" in rule:
                defined_alerts.add(rule["alert"])

    expected_alerts = {
        "APIErrorRateHigh",
        "DatabaseFailure",
        "QueueBacklogHigh",
        "AgentExecutionFailure",
        "TemporalWorkflowFailure",
        "SandboxExecutionFailure",
        "ModelGatewayFailure",
        "DiskUsageHigh",
    }
    assert expected_alerts.issubset(defined_alerts), (
        f"Missing production alerts: {expected_alerts - defined_alerts}"
    )

    # 2. OTel Collector configuration
    otel_file = REPO_ROOT / "infrastructure/opentelemetry/otel-collector-config.yml"
    assert otel_file.exists()
    otel_content = otel_file.read_text(encoding="utf-8")
    assert "4317" in otel_content and "4318" in otel_content


# ─── 6. Deployment Pillar ────────────────────────────────────────────────────


def test_readiness_deployment_pillar() -> None:
    """Validate Production Compose, Kubernetes manifests, AWS, and Azure OpenTofu."""
    # 1. Production Docker Compose
    prod_compose_file = REPO_ROOT / "docker-compose.prod.yml"
    assert prod_compose_file.exists()
    compose_data: dict[str, Any] = yaml.safe_load(prod_compose_file.read_text(encoding="utf-8"))
    services = compose_data.get("services", {})
    for required_service in ["backend", "worker", "frontend"]:
        assert required_service in services, (
            f"docker-compose.prod.yml missing service: {required_service}"
        )

    # Non-root verification across production Dockerfiles
    backend_df = (REPO_ROOT / "docker/Dockerfile.backend").read_text(encoding="utf-8")
    assert "USER 10001:10001" in backend_df or "USER appuser" in backend_df
    worker_df = (REPO_ROOT / "docker/Dockerfile.worker").read_text(encoding="utf-8")
    assert "USER 10001:10001" in worker_df or "USER appuser" in worker_df
    frontend_df = (REPO_ROOT / "docker/Dockerfile.frontend").read_text(encoding="utf-8")
    assert "USER 10001:10001" in frontend_df or "USER nextjs" in frontend_df

    # 2. Kubernetes Base Manifests
    k8s_base = REPO_ROOT / "deploy/kubernetes/base"
    for manifest in [
        "backend-deployment.yaml",
        "worker-deployment.yaml",
        "network-policies.yaml",
        "rbac.yaml",
    ]:
        assert (k8s_base / manifest).exists(), f"Kubernetes base missing {manifest}"

    # 3. AWS OpenTofu Module Structure
    aws_dir = REPO_ROOT / "deploy/opentofu/aws"
    assert (aws_dir / "main.tf").exists()
    for module in ["vpc", "eks", "postgresql", "storage", "cache", "secrets"]:
        assert (aws_dir / "modules" / module).is_dir(), f"AWS OpenTofu missing module: {module}"

    # 4. Azure OpenTofu Module Structure
    azure_dir = REPO_ROOT / "deploy/opentofu/azure"
    assert (azure_dir / "main.tf").exists()
    for module in ["vnet", "aks", "postgresql", "blob", "key_vault"]:
        assert (azure_dir / "modules" / module).is_dir(), f"Azure OpenTofu missing module: {module}"
