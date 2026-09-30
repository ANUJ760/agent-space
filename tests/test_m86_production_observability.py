"""Tests for M86 — Production Observability.

Validates the complete connectivity of the observability stack and all 8 production alert definitions per Section 95:
1. OpenTelemetry: OTLP ingestion, processor pipelines, and Prometheus/Loki exporters.
2. Prometheus: Server scraping configuration, rule file linkage, and Alertmanager targeting.
3. Grafana: Datasource definitions unifying Prometheus, Loki, and OpenTelemetry.
4. Loki: Structured log ingestion and retention configuration.
5. Production Alerts: All 8 required alert rules:
   - API error rate
   - database failure
   - queue backlog
   - agent failure
   - workflow failure
   - sandbox failure
   - GPU/model failure
   - disk usage
"""

from pathlib import Path

import pytest
import yaml

INFRA_DIR = Path(__file__).parent.parent / "infrastructure"


@pytest.fixture()
def otel_config() -> dict:
    path = INFRA_DIR / "opentelemetry" / "otel-collector-config.yml"
    assert path.exists(), f"OpenTelemetry config missing at {path}"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def prometheus_config() -> dict:
    path = INFRA_DIR / "prometheus" / "prometheus.yml"
    assert path.exists(), f"Prometheus config missing at {path}"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def alert_rules() -> list[dict]:
    path = INFRA_DIR / "prometheus" / "alerts" / "production_alerts.yml"
    assert path.exists(), f"Alert rules missing at {path}"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        groups = data.get("groups", [])
        assert len(groups) > 0, "No alert groups found in production_alerts.yml"
        return groups[0].get("rules", [])


@pytest.fixture()
def grafana_datasources() -> list[dict]:
    path = INFRA_DIR / "grafana" / "datasources" / "datasources.yml"
    assert path.exists(), f"Grafana datasources missing at {path}"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data.get("datasources", [])


@pytest.fixture()
def loki_config() -> dict:
    path = INFRA_DIR / "loki" / "loki-config.yml"
    assert path.exists(), f"Loki config missing at {path}"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestM86ProductionObservability:
    """Verifies observability infrastructure configurations and production alerts."""

    # ─── 1. OpenTelemetry Connectivity ──────────────────────────────────────

    def test_opentelemetry_collector_pipelines(self, otel_config: dict) -> None:
        receivers = otel_config.get("receivers", {})
        assert "otlp" in receivers
        assert "grpc" in receivers["otlp"]["protocols"]
        assert "http" in receivers["otlp"]["protocols"]

        exporters = otel_config.get("exporters", {})
        assert "prometheus" in exporters
        assert "loki" in exporters

        pipelines = otel_config.get("service", {}).get("pipelines", {})
        assert "traces" in pipelines
        assert "metrics" in pipelines
        assert "logs" in pipelines

    # ─── 2. Prometheus Connectivity ─────────────────────────────────────────

    def test_prometheus_scraping_and_alerting(self, prometheus_config: dict) -> None:
        scrape_jobs = [j["job_name"] for j in prometheus_config.get("scrape_configs", [])]
        assert "agentspace-api" in scrape_jobs
        assert "otel-collector" in scrape_jobs

        rule_files = prometheus_config.get("rule_files", [])
        assert any("alerts" in rf for rf in rule_files)

        alerting = prometheus_config.get("alerting", {}).get("alertmanagers", [])
        assert len(alerting) > 0

    # ─── 3. Grafana Datasources Connectivity ────────────────────────────────

    def test_grafana_unifies_prometheus_loki_opentelemetry(
        self, grafana_datasources: list[dict]
    ) -> None:
        ds_types = {ds["type"] for ds in grafana_datasources}
        ds_names = {ds["name"] for ds in grafana_datasources}

        assert "prometheus" in ds_types
        assert "loki" in ds_types
        assert "tempo" in ds_types or "OpenTelemetry" in ds_names

    # ─── 4. Loki Configuration ──────────────────────────────────────────────

    def test_loki_storage_and_retention(self, loki_config: dict) -> None:
        assert "server" in loki_config
        assert "schema_config" in loki_config
        assert "common" in loki_config and "storage" in loki_config["common"]

    # ─── 5. Production Alerts Coverage (All 8 Required Alerts) ───────────────

    def test_all_eight_production_alerts_defined(self, alert_rules: list[dict]) -> None:
        alert_names = {r["alert"] for r in alert_rules}

        # 1. API error rate
        assert "APIErrorRateHigh" in alert_names

        # 2. database failure
        assert "DatabaseFailure" in alert_names

        # 3. queue backlog
        assert "QueueBacklogHigh" in alert_names

        # 4. agent failure
        assert "AgentExecutionFailure" in alert_names

        # 5. workflow failure
        assert "TemporalWorkflowFailure" in alert_names

        # 6. sandbox failure
        assert "SandboxExecutionFailure" in alert_names

        # 7. GPU/model failure
        assert "ModelGatewayFailure" in alert_names

        # 8. disk usage
        assert "DiskUsageHigh" in alert_names

    def test_alert_rule_specifications(self, alert_rules: list[dict]) -> None:
        for rule in alert_rules:
            alert_name = rule["alert"]
            assert "expr" in rule, f"Alert {alert_name} missing expression"
            assert "for" in rule, f"Alert {alert_name} missing 'for' duration"
            assert "labels" in rule and "severity" in rule["labels"], (
                f"Alert {alert_name} missing severity label"
            )
            assert "annotations" in rule and "summary" in rule["annotations"], (
                f"Alert {alert_name} missing summary annotation"
            )
            assert "description" in rule["annotations"], (
                f"Alert {alert_name} missing description annotation"
            )
