# Agent Space Concurrency & Synchronization Model

Agent Space operates in a high-contention multi-tenant environment where human developers and autonomous AI agents concurrently manipulate shared codebases, database rows, and workflow state machines.

To ensure consistency, durability, and isolation, the platform enforces **six strict concurrency guarantees**.

---

## 1. Optimistic Locking (OCC)

Every mutable aggregate (`Project`, `Task`, `Agent`) maintains an integer `version` attribute incremented atomically on every mutation.

### Pattern:
```python
# Atomic version verification on UPDATE
stmt = (
    update(Task)
    .where(Task.id == task_id, Task.version == expected_version)
    .values(status=new_status, version=Task.version + 1)
)
result = await session.execute(stmt)
if result.rowcount == 0:
    raise ConflictError(
        code="VERSION_CONFLICT",
        message="Resource was concurrently modified by another actor."
    )
```

Clients submit `expected_version` in payloads. If a race condition occurs, the request aborts with `409 Conflict`, allowing the client to reload authoritative state.

---

## 2. Row-Level Pessimistic Locking (`SELECT FOR UPDATE`)

For operations where multiple concurrent agents attempt to claim the same task simultaneously, or where a human operator initiates an emergency task takeover:

```python
# Acquire row lock exclusively within the transaction
stmt = select(Task).where(Task.id == task_id).with_for_update()
task = (await session.execute(stmt)).scalar_one_or_none()
```

- Blocks competing transactions until the first transaction commits or rolls back.
- Guarantees exactly-one agent wins the claim.
- Ensures human takeovers atomically invalidate active agent execution.

---

## 3. Idempotency Keys

All state-mutating endpoints (`POST /tasks`, `POST /tasks/{id}/assign`, `POST /tasks/{id}/requests/respond`) accept an optional `Idempotency-Key` HTTP header.

### Mechanics:
1. When an `Idempotency-Key` is received, the backend checks Redis:
   - Key: `idempotency:{org_id}:{key}`
2. If the key exists:
   - Returns the cached response immediately without re-executing business logic or creating duplicate tasks.
3. If the key does not exist:
   - Locks the key with a temporary `IN_FLIGHT` marker (TTL 60s).
   - Executes the request.
   - Replaces the marker with the final HTTP status and response payload (TTL 24 hours).

---

## 4. Transactional Outbox & Event Deduplication

To prevent distributed two-phase commit failures between PostgreSQL and NATS / Redis:

1. **Atomic Outbox Write**: State changes and domain events (`OutboxEvent`) are inserted inside the **same SQL transaction**.
2. **Outbox Publisher**: A background polling daemon reads unhandled events in order (`ORDER BY created_at ASC`), dispatches them to NATS JetStream, and marks them `published_at = NOW()`.
3. **Consumer Deduplication**: Consumers track `event.id` (UUIDv4) in Redis deduplication bloom filters / sets, guaranteeing **at-least-once transport with exactly-once consumer execution**.

---

## 5. Git Isolation & Worktree Partitioning

Autonomous coding agents executing parallel tasks on the same project repository must never corrupt Git index files or clash over HEAD.

### Partitioning Rules:
- **Dedicated Agent Branches**: Agents work exclusively on ephemeral task branches:
  `agents/{agent_id}/{task_id}`
- **Ephemeral Worktrees**: Each agent sandbox mounts a distinct Git worktree in an isolated filesystem volume (`/workspace/worktrees/{task_id}`).
- **Atomic Fast-Forward Merges**: Only when a task passes tests and receives reviewer sign-off does the reviewer or human merge the branch into `main`.

---

## 6. Durable Workflow Recovery (Temporal)

Long-running agent planning, coding, and review loops execute inside **Temporal Workflows** (`TaskWorkflow`):

- **Zero Lost State**: State mutations are recorded in Temporal's event history. If a worker pod crashes or restarts, Temporal automatically rehydrates workflow state by replaying non-deterministic activity completions.
- **Durable Signals**: Human intervention (pause, resume, human input, takeover, approval) is signaled asynchronously via durable Temporal signals (`workflow.signal`).
- **Heartbeats**: Activities stream progress heartbeats every 5 seconds. If a worker fails silently, Temporal detects timeout within 15 seconds and reassigns the task to an available healthy worker.
