# Agent Space Durable Workflows & Orchestration Specification

Agent Space coordinates long-running agent loops, multi-step engineering pipelines, and human checkpoints through **Temporal** durable workflows.

---

## 1. Why Temporal?

Autonomous engineering tasks span minutes to hours. Traditional HTTP polling or Celery tasks suffer from:
- Lost execution state when worker pods restart.
- Complex state recovery logic on network partitions.
- Difficult human-in-the-loop pause and signal semantics.

Temporal provides **durable execution**: execution state, timers, and signals are persisted durably in event histories, allowing workflows to pause indefinitely, survive restarts, and resume exactly where they left off.

---

## 2. Core Workflow: `TaskWorkflow`

Located in `apps/backend/app/temporal/workflows/task_workflow.py`.

```text
[LOAD_TASK] ──> [VALIDATE_DEPENDENCIES] ──> [CLAIM] ──> [EXECUTE_WORKER]
                                                            │
    (Approved)               (Wait Condition)               ▼
[FINISH / DONE] <──── [WAITING_FOR_APPROVAL] <──── (require_approval?)
```

### Execution Steps:
1. **LOAD_TASK**: Retrieves task definition and context from PostgreSQL.
2. **VALIDATE_DEPENDENCIES**: Verifies all prerequisite task DAG dependencies are in `DONE` status; blocks if unmet.
3. **CLAIM**: Acquires optimistic row lock and marks task `CLAIMED` by assigned agent.
4. **EXECUTE_WORKER**: Dispatches cognitive loop to agent runtime within an isolated sandbox.
5. **APPROVAL CHECK**: If task requires human sign-off, suspends execution durably until `approval` signal is delivered.
6. **FINISH**: Updates task status to `DONE` and commits output artifacts to Content-Addressable Storage.

---

## 3. Durable Signals & Human-in-the-Loop

Workflows wait on non-polling durable conditions (`await workflow.wait_condition(...)`).

### Supported Signals:

| Signal | Arguments | Description |
|---|---|---|
| `pause` | none | Suspends workflow execution between activity steps. |
| `resume` | none | Resumes a previously paused workflow. |
| `human_input` | `{"data": ...}` | Delivers user responses to agent clarification requests. |
| `approval` | `{"approved": bool, "reason": str}` | Approves or rejects changes before completion. |
| `takeover` | `{"user_id": str}` | Transfers execution authority immediately to a human engineer. |
| `handoff` | `{"to_entity_id": str, ...}` | Reassigns active task context to a successor agent. |

---

## 4. Workflow Queries

External callers (FastAPI endpoints and WebSocket gateways) inspect live workflow status synchronously via queries:

- `state()`: Complete workflow internal state (current step, error status, taken_over_by, handoff).
- `is_paused()`: Boolean indicating if workflow is currently in a paused state.
- `pending_human_input()`: Active question or approval prompt awaiting human action.

---

## 5. Activity Timeouts & Retry Policies

Activities run under standardized retry and heartbeat policies:

```python
RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    non_retryable_error_types=["PermissionError", "ValidationError"]
)
```

- **Activity Heartbeats**: Long-running workers send heartbeats every 5 seconds.
- **Worker Failure Detection**: If heartbeats cease for >15 seconds, Temporal marks the activity timed out and reschedules it on an alternate worker.
