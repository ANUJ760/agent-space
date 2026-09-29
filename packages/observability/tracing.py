"""OpenTelemetry distributed tracing and correlation framework (M68).

Traces the full execution path:
    HTTP request
        ↓
    service
        ↓
    database
        ↓
    workflow
        ↓
    agent
        ↓
    tool
        ↓
    sandbox

Correlates:
- request_id
- project_id
- task_id
- workflow_id
- agent_session_id
- tool_call_id
"""

import inspect
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, StatusCode, Tracer

CORRELATION_KEYS = [
    "request_id",
    "project_id",
    "task_id",
    "workflow_id",
    "agent_session_id",
    "tool_call_id",
]

# Pipeline stages
STAGE_HTTP_REQUEST = "http.request"
STAGE_SERVICE = "service.execution"
STAGE_DATABASE = "database.query"
STAGE_WORKFLOW = "temporal.workflow"
STAGE_AGENT = "agent.execution"
STAGE_TOOL = "tool.gateway"
STAGE_SANDBOX = "sandbox.docker"


@dataclass
class TraceCorrelationContext:
    """Carries correlation identifiers through asynchronous execution contexts."""

    request_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    workflow_id: str | None = None
    agent_session_id: str | None = None
    tool_call_id: str | None = None

    def to_attributes(self) -> dict[str, str]:
        """Convert non-empty IDs into OpenTelemetry span attributes."""
        attrs: dict[str, str] = {}
        for key in CORRELATION_KEYS:
            val = getattr(self, key, None)
            if val:
                attrs[f"agentspace.{key}"] = str(val)
        return attrs


_current_trace_context: ContextVar[TraceCorrelationContext | None] = ContextVar(
    "current_trace_context",
    default=None,
)


def get_trace_correlation() -> TraceCorrelationContext:
    """Return the active correlation context for the current async task."""
    ctx = _current_trace_context.get()
    return ctx if ctx is not None else TraceCorrelationContext()


def set_trace_correlation(context: TraceCorrelationContext) -> None:
    """Set the active correlation context."""
    _current_trace_context.set(context)


def update_trace_correlation(**kwargs: Any) -> TraceCorrelationContext:
    """Update correlation keys in the current context."""
    current = get_trace_correlation()
    updated = TraceCorrelationContext(
        request_id=kwargs.get("request_id", current.request_id),
        project_id=kwargs.get("project_id", current.project_id),
        task_id=kwargs.get("task_id", current.task_id),
        workflow_id=kwargs.get("workflow_id", current.workflow_id),
        agent_session_id=kwargs.get("agent_session_id", current.agent_session_id),
        tool_call_id=kwargs.get("tool_call_id", current.tool_call_id),
    )
    _current_trace_context.set(updated)
    return updated


@contextmanager
def trace_correlation_scope(**kwargs: Any) -> Iterator[TraceCorrelationContext]:
    """Context manager setting scoped correlation keys for a block of code."""
    token = _current_trace_context.set(
        TraceCorrelationContext(
            request_id=kwargs.get("request_id"),
            project_id=kwargs.get("project_id"),
            task_id=kwargs.get("task_id"),
            workflow_id=kwargs.get("workflow_id"),
            agent_session_id=kwargs.get("agent_session_id"),
            tool_call_id=kwargs.get("tool_call_id"),
        )
    )
    try:
        yield _current_trace_context.get()
    finally:
        _current_trace_context.reset(token)


class TelemetryManager:
    """Manages OpenTelemetry tracer lifecycle and span exporters."""

    def __init__(self) -> None:
        self._provider: TracerProvider | None = None
        self._tracer: Tracer | None = None
        self._memory_exporter: InMemorySpanExporter | None = None

    def initialize(
        self,
        service_name: str = "agent-space-backend",
        in_memory: bool = False,
    ) -> Tracer:
        """Initialize OpenTelemetry tracer provider with appropriate processors."""
        if self._provider is None:
            resource = Resource.create({"service.name": service_name})
            self._provider = TracerProvider(resource=resource)
            if in_memory:
                self._memory_exporter = InMemorySpanExporter()
                self._provider.add_span_processor(SimpleSpanProcessor(self._memory_exporter))
            with suppress(Exception):
                trace.set_tracer_provider(self._provider)
            self._tracer = self._provider.get_tracer(service_name)
        elif in_memory and self._memory_exporter is None:
            self._memory_exporter = InMemorySpanExporter()
            self._provider.add_span_processor(SimpleSpanProcessor(self._memory_exporter))

        return self.tracer

    @property
    def tracer(self) -> Tracer:
        if self._tracer is None:
            self.initialize()
        assert self._tracer is not None
        return self._tracer

    @property
    def memory_exporter(self) -> InMemorySpanExporter | None:
        return self._memory_exporter

    def get_finished_spans(self) -> list[Any]:
        """Return recorded spans from memory exporter (useful for testing/audits)."""
        if self._memory_exporter:
            return list(self._memory_exporter.get_finished_spans())
        return []

    def clear(self) -> None:
        """Clear recorded spans in memory exporter."""
        if self._memory_exporter:
            self._memory_exporter.clear()


_telemetry_manager = TelemetryManager()


def get_telemetry_manager() -> TelemetryManager:
    """Return the global TelemetryManager instance."""
    return _telemetry_manager


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[Span]:
    """Synchronous context manager creating a traced span with active correlation IDs."""
    tracer = get_telemetry_manager().tracer
    corr = get_trace_correlation()
    all_attrs = {**corr.to_attributes(), **attributes}

    with tracer.start_as_current_span(name, attributes=all_attrs) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise


@asynccontextmanager
async def async_trace_span(name: str, **attributes: Any) -> AsyncIterator[Span]:
    """Asynchronous context manager creating a traced span with active correlation IDs."""
    tracer = get_telemetry_manager().tracer
    corr = get_trace_correlation()
    all_attrs = {**corr.to_attributes(), **attributes}

    with tracer.start_as_current_span(name, attributes=all_attrs) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise


def traced(span_name: str | None = None) -> Callable[..., Any]:
    """Decorator to trace a sync or async function automatically with correlation context."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        target_name = span_name or func.__name__

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            async with async_trace_span(target_name):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(target_name):
                return func(*args, **kwargs)
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
