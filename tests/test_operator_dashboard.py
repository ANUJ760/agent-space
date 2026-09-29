"""Tests for M72: Operational Telemetry & Single Operator Dashboard."""

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_operator_dashboard_api_endpoint():
    settings = Settings(
        environment="test",
        debug=True,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings)
    client = TestClient(app)

    res = client.get("/api/v1/operator/dashboard")
    assert res.status_code == 200
    data = res.json()

    # Verify all 9 required operational telemetry metrics are present
    required_fields = [
        "system_health",
        "active_workflows",
        "agent_health",
        "queue_depth",
        "failed_tasks",
        "sandbox_failures",
        "api_errors",
        "model_latency_p95_ms",
        "database_health",
    ]

    for field in required_fields:
        assert field in data, f"Operator dashboard payload missing field: {field}"

    assert data["system_health"] in {"HEALTHY", "DEGRADED", "UNHEALTHY"}
    assert data["database_health"] in {"UP", "DOWN"}
    assert isinstance(data["agent_health"], dict)
    assert isinstance(data["queue_depth"], dict)


def test_grafana_operator_dashboard_spec():
    op_path = Path("infrastructure/grafana/dashboards/operator.json")
    assert op_path.exists(), "operator.json dashboard missing"

    with open(op_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["uid"] == "agentspace-operator"
    assert "panels" in data
    # Must have all 9 operational panels
    assert len(data["panels"]) == 9

    panel_titles = [p["title"] for p in data["panels"]]
    assert "System Health" in panel_titles
    assert "Active Workflows" in panel_titles
    assert "Agent Health & Availability" in panel_titles
    assert "Queue Depth" in panel_titles
    assert "Failed Tasks Rate" in panel_titles
    assert "Sandbox Failures" in panel_titles
    assert "API Errors" in panel_titles
    assert "Model Latency (p95)" in panel_titles
    assert "Database Health" in panel_titles
