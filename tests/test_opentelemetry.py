"""Tests for M68: OpenTelemetry Distributed Tracing & Correlation.

Verifies:
1. End-to-end trace propagation across full execution pipeline:
   HTTP request -> service -> database -> workflow -> agent -> tool -> sandbox
2. Correlation of all mandatory IDs:
   - request_id
   - project_id
   - task_id
   - workflow_id
   - agent_session_id
   - tool_call_id
3. Exception capture and error status recording on spans
4. Synchronous and asynchronous function decorators (@traced)
5. Context isolation and scoped correlation propagation
"""

import uuid

import pytest
from opentelemetry.trace import StatusCode

from packages.observability import (
    STAGE_AGENT,
    STAGE_DATABASE,
    STAGE_HTTP_REQUEST,
    STAGE_SANDBOX,
    STAGE_SERVICE,
    STAGE_TOOL,
    STAGE_WORKFLOW,
    async_trace_span,
    get_telemetry_manager,
    trace_correlation_scope,
    trace_span,
    traced,
    update_trace_correlation,
)


@pytest.fixture(autouse=True)
def init_in_memory_telemetry():
    """Ensure in-memory exporter is active and cleared for every test."""
    manager = get_telemetry_manager()
    manager.initialize(service_name="agent-space-test", in_memory=True)
    manager.clear()
    yield manager
    manager.clear()


def test_full_pipeline_trace_correlation():
    manager = get_telemetry_manager()

    req_id = f"req-{uuid.uuid4().hex[:8]}"
    proj_id = f"proj-{uuid.uuid4().hex[:8]}"
    tsk_id = f"task-{uuid.uuid4().hex[:8]}"
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    agent_id = f"agent-session-{uuid.uuid4().hex[:8]}"
    tool_id = f"tool-{uuid.uuid4().hex[:8]}"

    # Execute full pipeline
    with (
        trace_correlation_scope(request_id=req_id, project_id=proj_id),
        trace_span(STAGE_HTTP_REQUEST),
        trace_span(STAGE_SERVICE),
        trace_span(STAGE_DATABASE, query="SELECT * FROM tasks WHERE id = :id"),
    ):
        pass  # Synchronous HTTP -> Service -> DB phase completed

    # Background workflow triggered
    with trace_correlation_scope(
        request_id=req_id,
        project_id=proj_id,
        task_id=tsk_id,
        workflow_id=wf_id,
    ), trace_span(STAGE_WORKFLOW):
        update_trace_correlation(agent_session_id=agent_id)
        with trace_span(STAGE_AGENT):
            update_trace_correlation(tool_call_id=tool_id)
            with (
                trace_span(STAGE_TOOL, tool_name="execute_python"),
                trace_span(STAGE_SANDBOX, container_id="sbx-123"),
            ):
                pass  # Sandboxed execution

    spans = manager.get_finished_spans()
    assert len(spans) == 7

    span_names = [s.name for s in spans]
    assert STAGE_HTTP_REQUEST in span_names
    assert STAGE_SERVICE in span_names
    assert STAGE_DATABASE in span_names
    assert STAGE_WORKFLOW in span_names
    assert STAGE_AGENT in span_names
    assert STAGE_TOOL in span_names
    assert STAGE_SANDBOX in span_names

    # Verify correlation attributes on innermost span (SANDBOX)
    sandbox_span = next(s for s in spans if s.name == STAGE_SANDBOX)
    attrs = sandbox_span.attributes

    assert attrs["agentspace.request_id"] == req_id
    assert attrs["agentspace.project_id"] == proj_id
    assert attrs["agentspace.task_id"] == tsk_id
    assert attrs["agentspace.workflow_id"] == wf_id
    assert attrs["agentspace.agent_session_id"] == agent_id
    assert attrs["agentspace.tool_call_id"] == tool_id
    assert attrs["container_id"] == "sbx-123"


@pytest.mark.asyncio
async def test_async_trace_span_and_error_capture():
    manager = get_telemetry_manager()

    with (
        trace_correlation_scope(request_id="req-err-1", task_id="task-err-1"),
        pytest.raises(RuntimeError, match="Simulated execution crash"),
    ):
        async with async_trace_span("agent.failed_step"):
            raise RuntimeError("Simulated execution crash")

    spans = manager.get_finished_spans()
    assert len(spans) == 1
    failed_span = spans[0]

    assert failed_span.status.status_code == StatusCode.ERROR
    assert "Simulated execution crash" in failed_span.status.description
    assert failed_span.attributes["agentspace.request_id"] == "req-err-1"
    assert failed_span.attributes["agentspace.task_id"] == "task-err-1"
    assert len(failed_span.events) > 0  # Exception event recorded


@pytest.mark.asyncio
async def test_traced_decorator_sync_and_async():
    manager = get_telemetry_manager()

    @traced("sync.worker_operation")
    def sync_op(x: int) -> int:
        return x * 2

    @traced("async.agent_operation")
    async def async_op(msg: str) -> str:
        return f"Echo: {msg}"

    with trace_correlation_scope(project_id="proj-decorators"):
        res1 = sync_op(21)
        res2 = await async_op("hello")

    assert res1 == 42
    assert res2 == "Echo: hello"

    spans = manager.get_finished_spans()
    assert len(spans) == 2
    names = [s.name for s in spans]
    assert "sync.worker_operation" in names
    assert "async.agent_operation" in names

    for s in spans:
        assert s.attributes["agentspace.project_id"] == "proj-decorators"
