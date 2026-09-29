"""Tests for M69: Prometheus Metrics Instrumentation.

Validates:
1. Prometheus scraping endpoint GET /metrics
2. Collection and formatting of all 16 required platform metrics:
   - api_requests_total, api_latency, api_errors_total
   - task_created_total, task_completed_total, task_failed_total, task_conflict_total
   - agent_execution_total, agent_execution_duration
   - workflow_started_total, workflow_failed_total
   - tool_calls_total, sandbox_execution_duration
   - websocket_connections, queue_depth, model_latency
3. Automatic API request tracking via middleware
"""

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from packages.observability import MetricsRegistry


def test_metrics_registry_recording():
    custom_reg = CollectorRegistry()
    metrics = MetricsRegistry(registry=custom_reg)

    # 1. API metrics
    metrics.api_requests_total.labels(method="POST", path="/api/v1/tasks", status="201").inc()
    metrics.api_latency.labels(method="POST", path="/api/v1/tasks").observe(0.045)
    metrics.api_errors_total.labels(error_code="409", error_type="client_error").inc()

    # 2. Task lifecycle metrics
    metrics.task_created_total.labels(priority="HIGH").inc()
    metrics.task_completed_total.labels(status="DONE").inc()
    metrics.task_failed_total.labels(reason="EXECUTION_TIMEOUT").inc()
    metrics.task_conflict_total.labels(conflict_type="VERSION_MISMATCH").inc()

    # 3. Agent execution metrics
    metrics.agent_execution_total.labels(agent_role="DEVELOPER", status="SUCCESS").inc()
    metrics.agent_execution_duration.labels(agent_role="DEVELOPER").observe(1.25)

    # 4. Workflow metrics
    metrics.workflow_started_total.labels(workflow_type="TaskExecutionWorkflow").inc()
    metrics.workflow_failed_total.labels(workflow_type="TaskExecutionWorkflow").inc()

    # 5. Tool & Sandbox metrics
    metrics.tool_calls_total.labels(tool_name="git_diff", status="SUCCESS").inc()
    metrics.sandbox_execution_duration.labels(sandbox_type="docker").observe(0.85)

    # 6. Operational gauges
    metrics.websocket_connections.set(14)
    metrics.queue_depth.labels(queue_name="agent-task-queue").set(3)
    metrics.model_latency.labels(model="claude-3-5-sonnet", provider="anthropic").observe(0.42)

    output = metrics.generate_metrics().decode("utf-8")

    # Verify all metric names are present in output
    expected_metrics = [
        "api_requests_total",
        "api_latency",
        "api_errors_total",
        "task_created_total",
        "task_completed_total",
        "task_failed_total",
        "task_conflict_total",
        "agent_execution_total",
        "agent_execution_duration",
        "workflow_started_total",
        "workflow_failed_total",
        "tool_calls_total",
        "sandbox_execution_duration",
        "websocket_connections",
        "queue_depth",
        "model_latency",
    ]

    for metric in expected_metrics:
        assert metric in output, f"Missing metric {metric} in Prometheus exposition output"


def test_metrics_endpoint_and_middleware():
    settings = Settings(
        environment="test",
        debug=True,
        database_url="sqlite+aiosqlite:///:memory:",
        prometheus_metrics_enabled=True,
    )
    app = create_app(settings)
    client = TestClient(app)

    # Trigger request through middleware
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200

    # Scrape /metrics endpoint
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    assert "text/plain" in metrics_res.headers["content-type"]

    body = metrics_res.text
    assert "api_requests_total" in body
    assert "api_latency" in body
    assert "/api/v1/health/live" in body
