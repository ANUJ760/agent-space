"""Tests for M70: Grafana Dashboards and Provisioning Configuration."""

import json
from pathlib import Path


def test_grafana_dashboards_validity():
    dashboards_dir = Path("infrastructure/grafana/dashboards")
    assert dashboards_dir.exists(), "Grafana dashboards directory must exist"

    expected_dashboards = [
        "api.json",
        "agents.json",
        "temporal.json",
        "nats.json",
        "database.json",
        "redis.json",
        "sandbox.json",
        "models.json",
    ]

    for filename in expected_dashboards:
        path = dashboards_dir / filename
        assert path.exists(), f"Dashboard {filename} is missing"

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        assert "title" in data
        assert "uid" in data
        assert "panels" in data
        assert len(data["panels"]) >= 2, f"Dashboard {filename} must contain at least 2 panels"

        for panel in data["panels"]:
            assert "title" in panel
            assert "type" in panel
            assert "targets" in panel
            assert len(panel["targets"]) >= 1


def test_grafana_provisioning_config():
    ds_path = Path("infrastructure/grafana/datasources/prometheus.yml")
    assert ds_path.exists(), "Prometheus datasource provisioning file missing"
    content_ds = ds_path.read_text(encoding="utf-8")
    assert "Prometheus" in content_ds
    assert "url: http://prometheus:9090" in content_ds

    dash_prov_path = Path("infrastructure/grafana/dashboards/dashboards.yml")
    assert dash_prov_path.exists(), "Dashboard provider configuration missing"
    content_dash = dash_prov_path.read_text(encoding="utf-8")
    assert "Agent Space" in content_dash or "AgentSpace" in content_dash
