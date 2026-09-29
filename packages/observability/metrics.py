"""Prometheus metrics instrumentation for Agent Space platform (M69).

Collects:
- API metrics: api_requests_total, api_latency, api_errors_total
- Task metrics: task_created_total, task_completed_total, task_failed_total, task_conflict_total
- Agent metrics: agent_execution_total, agent_execution_duration
- Workflow metrics: workflow_started_total, workflow_failed_total
- Tool & Sandbox: tool_calls_total, sandbox_execution_duration
- System gauges: websocket_connections, queue_depth, model_latency
"""

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Standard latency buckets (in seconds)
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class MetricsRegistry:
    """Encapsulates all platform Prometheus metrics for runtime instrumentation and testing."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()

        # ─── 1. API Metrics ────────────────────────────────────────────────
        self.api_requests_total = Counter(
            "api_requests_total",
            "Total count of HTTP requests processed by API",
            ["method", "path", "status"],
            registry=self.registry,
        )
        self.api_latency = Histogram(
            "api_latency",
            "HTTP request processing latency in seconds",
            ["method", "path"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.api_errors_total = Counter(
            "api_errors_total",
            "Total count of HTTP request errors",
            ["error_code", "error_type"],
            registry=self.registry,
        )

        # ─── 2. Task Lifecycle Metrics ─────────────────────────────────────
        self.task_created_total = Counter(
            "task_created_total",
            "Total tasks created in Agent Space",
            ["priority"],
            registry=self.registry,
        )
        self.task_completed_total = Counter(
            "task_completed_total",
            "Total tasks successfully completed",
            ["status"],
            registry=self.registry,
        )
        self.task_failed_total = Counter(
            "task_failed_total",
            "Total tasks ending in failure",
            ["reason"],
            registry=self.registry,
        )
        self.task_conflict_total = Counter(
            "task_conflict_total",
            "Total task optimistic concurrency or assignment conflicts (409)",
            ["conflict_type"],
            registry=self.registry,
        )

        # ─── 3. Agent Execution Metrics ────────────────────────────────────
        self.agent_execution_total = Counter(
            "agent_execution_total",
            "Total agent execution steps executed",
            ["agent_role", "status"],
            registry=self.registry,
        )
        self.agent_execution_duration = Histogram(
            "agent_execution_duration",
            "Duration of agent task execution cycle in seconds",
            ["agent_role"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        # ─── 4. Workflow (Temporal) Metrics ────────────────────────────────
        self.workflow_started_total = Counter(
            "workflow_started_total",
            "Total durable workflows initiated",
            ["workflow_type"],
            registry=self.registry,
        )
        self.workflow_failed_total = Counter(
            "workflow_failed_total",
            "Total durable workflows failed",
            ["workflow_type"],
            registry=self.registry,
        )

        # ─── 5. Tool & Sandbox Execution Metrics ───────────────────────────
        self.tool_calls_total = Counter(
            "tool_calls_total",
            "Total tool invocations dispatched",
            ["tool_name", "status"],
            registry=self.registry,
        )
        self.sandbox_execution_duration = Histogram(
            "sandbox_execution_duration",
            "Duration of isolated container sandbox executions in seconds",
            ["sandbox_type"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        # ─── 6. Realtime & Operational Gauges ──────────────────────────────
        self.websocket_connections = Gauge(
            "websocket_connections",
            "Number of currently active WebSocket client connections",
            registry=self.registry,
        )
        self.queue_depth = Gauge(
            "queue_depth",
            "Current pending message or task queue depth",
            ["queue_name"],
            registry=self.registry,
        )
        self.model_latency = Histogram(
            "model_latency",
            "Foundation LLM model response latency in seconds",
            ["model", "provider"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

    def generate_metrics(self) -> bytes:
        """Serialize current metric values into Prometheus exposition text format."""
        return generate_latest(self.registry)


_default_metrics = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    """Return default singleton metrics registry."""
    return _default_metrics


def create_metrics_router(metrics_registry: MetricsRegistry | None = None) -> APIRouter:
    """Create FastAPI router exposing standard Prometheus scraping endpoint."""
    router = APIRouter(tags=["Observability"])
    reg = metrics_registry or get_metrics()

    @router.get("/metrics", summary="Prometheus Metrics Endpoint", include_in_schema=False)
    def metrics_endpoint() -> Response:
        """Scrape endpoint consumed by Prometheus."""
        data = reg.generate_metrics()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return router
