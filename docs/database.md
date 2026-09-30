# Agent Space Database Architecture & Schema Specification

PostgreSQL 16 serves as the **authoritative single source of truth** for all persistent application state.

---

## 1. Schema Invariants & Design Principles

1. **UUIDv4 Primary Keys**: All tables use random UUIDv4 (`UUIDPrimaryKeyMixin`) to prevent sequential enumeration attacks and facilitate distributed record generation.
2. **Deterministic Timestamps**: `created_at` and `updated_at` are managed via `TimestampMixin` with UTC timezone enforcement.
3. **Optimistic Concurrency Control**: Core mutable entities (`Project`, `Task`, `Agent`) inherit `VersionMixin` maintaining an integer `version` incremented on every write to prevent lost updates.
4. **Row-Level Locking**: High-contention transitions (task claiming, human takeover, agent handoff) execute atomic `SELECT ... FOR UPDATE` row locks.
5. **Transactional Outbox Pattern**: State mutations and associated event emissions are committed atomically in the same database transaction via `outbox_events`.

---

## 2. Entity Relational Model

```text
┌─────────────────┐       ┌─────────────────┐
│  organizations  │───┬──<│      users      │
└────────┬────────┘   │   └────────┬────────┘
         │            │            │
         │            └──<┌────────┴────────┐
         │                │     projects    │
         │                └────────┬────────┘
         │                         │
         │   ┌─────────────────────┼─────────────────────┐
         │   │                     │                     │
         ▼   ▼                     ▼                     ▼
┌─────────────────┐       ┌─────────────────┐   ┌─────────────────┐
│     agents      │       │      tasks      │   │ project_members │
└─────────────────┘       └────────┬────────┘   └─────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
         ┌───────────────────┐         ┌───────────────────┐
         │ task_dependencies │         │     artifacts     │
         └───────────────────┘         └───────────────────┘
```

---

## 3. Core Tables

### 1. `organizations`
- `id`: UUID (PK)
- `name`: VARCHAR(255), NOT NULL
- `slug`: VARCHAR(255), UNIQUE, NOT NULL, INDEX
- `created_at`, `updated_at`: TIMESTAMP WITH TIME ZONE

### 2. `users`
- `id`: UUID (PK)
- `organization_id`: UUID, FK -> `organizations.id` (CASCADE)
- `external_subject`: VARCHAR(255), UNIQUE, NOT NULL (OIDC Subject)
- `email`: VARCHAR(255), NOT NULL, INDEX
- `username`: VARCHAR(255), NOT NULL
- `role`: VARCHAR(50), NOT NULL (`ORG_ADMIN`, `PROJECT_MAINTAINER`, `PROJECT_MEMBER`, `OBSERVER`)
- `is_active`: BOOLEAN, DEFAULT TRUE

### 3. `projects`
- `id`: UUID (PK)
- `organization_id`: UUID, FK -> `organizations.id` (CASCADE)
- `name`: VARCHAR(255), NOT NULL
- `slug`: VARCHAR(255), NOT NULL, INDEX
- `description`: VARCHAR(4096), NULL
- `status`: VARCHAR(50), DEFAULT 'ACTIVE' (`ACTIVE`, `ARCHIVED`, `PAUSED`)
- `repository_url`: VARCHAR(1024), NULL
- `default_branch`: VARCHAR(255), DEFAULT 'main'
- `version`: INTEGER, DEFAULT 1

### 4. `tasks`
- `id`: UUID (PK)
- `organization_id`: UUID, FK -> `organizations.id` (CASCADE)
- `project_id`: UUID, FK -> `projects.id` (CASCADE)
- `title`: VARCHAR(255), NOT NULL, INDEX
- `description`: VARCHAR(4096), NULL
- `status`: VARCHAR(50), NOT NULL, DEFAULT 'TODO' (`TODO`, `CLAIMED`, `IN_PROGRESS`, `REVIEW`, `DONE`, `BLOCKED`, `PAUSED`, `FAILED`, `CANCELLED`)
- `priority`: VARCHAR(50), NOT NULL, DEFAULT 'MEDIUM' (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- `assigned_agent_id`: UUID, FK -> `agents.id` (SET NULL)
- `assigned_user_id`: UUID, FK -> `users.id` (SET NULL)
- `created_by_id`: UUID, FK -> `users.id` (SET NULL)
- `context`: JSONB, DEFAULT '{}' (Stores runtime parameters, human requests, scratchpad metadata)
- `version`: INTEGER, DEFAULT 1

### 5. `task_dependencies`
- `id`: UUID (PK)
- `task_id`: UUID, FK -> `tasks.id` (CASCADE), INDEX
- `depends_on_task_id`: UUID, FK -> `tasks.id` (CASCADE), INDEX
- Constraint: UNIQUE (`task_id`, `depends_on_task_id`)

### 6. `agents`
- `id`: UUID (PK)
- `organization_id`: UUID, FK -> `organizations.id` (CASCADE)
- `name`: VARCHAR(255), NOT NULL
- `slug`: VARCHAR(255), NOT NULL
- `role`: VARCHAR(50), NOT NULL (`COORDINATOR`, `RESEARCHER`, `ARCHITECT`, `DEVELOPER`, `TESTER`, `REVIEWER`)
- `model`: VARCHAR(255), DEFAULT 'llama3.1:8b'
- `model_provider`: VARCHAR(50), DEFAULT 'ollama'
- `status`: VARCHAR(50), DEFAULT 'READY' (`READY`, `BUSY`, `OFFLINE`)
- `capabilities`: JSONB, DEFAULT '[]'
- `workload_active_tasks`: INTEGER, DEFAULT 0
- `workload_max_concurrent`: INTEGER, DEFAULT 3
- `version`: INTEGER, DEFAULT 1

### 7. `artifacts`
- `id`: UUID (PK)
- `organization_id`: UUID, FK -> `organizations.id` (CASCADE)
- `project_id`: UUID, FK -> `projects.id` (SET NULL)
- `task_id`: UUID, FK -> `tasks.id` (SET NULL)
- `storage_key`: VARCHAR(1024), NOT NULL (Content-addressed SHA-256)
- `filename`: VARCHAR(255), NOT NULL
- `content_type`: VARCHAR(100), NOT NULL
- `size_bytes`: BIGINT, NOT NULL
- `sha256_hash`: VARCHAR(64), NOT NULL
- `artifact_type`: VARCHAR(50), NOT NULL (`DIFF`, `TEST_REPORT`, `CODE_REVIEW`, `SPEC`, `LOG`)
- `metadata_json`: JSONB, NULL

### 8. `outbox_events`
- `id`: UUID (PK)
- `organization_id`: UUID, FK -> `organizations.id` (CASCADE)
- `project_id`: UUID, FK -> `projects.id` (CASCADE)
- `event_type`: VARCHAR(100), NOT NULL (`task.updated`, `task.assigned`, `human.input_required`, `workflow.updated`, etc.)
- `aggregate_type`: VARCHAR(100), NOT NULL (`task`, `project`, `agent`)
- `aggregate_id`: UUID, NOT NULL
- `payload`: JSONB, NOT NULL
- `published_at`: TIMESTAMP WITH TIME ZONE, NULL
- `created_at`: TIMESTAMP WITH TIME ZONE, DEFAULT NOW()

---

## 4. Concurrency & Locking Mechanics

### Optimistic Concurrency Control (OCC)
Updates require providing the `expected_version`. If another process modified the row concurrently:
```sql
UPDATE tasks
SET status = 'IN_PROGRESS', version = version + 1
WHERE id = :task_id AND version = :expected_version;
```
If 0 rows are updated, a `ConflictError(409)` is raised immediately.

### Row-Level Locking (Pessimistic Locking)
For atomic takeovers and assignments:
```sql
SELECT * FROM tasks WHERE id = :task_id FOR UPDATE;
```
Acquires an exclusive lock on the row for the transaction duration, guaranteeing zero race conditions between concurrent agent claims and human interventions.

---

## 5. Database Migrations
Migrations are authored using **Alembic** under `apps/backend/alembic/`.
- Run migrations: `alembic upgrade head`
- Rollback migration: `alembic downgrade -1`
- Generate new revision: `alembic revision --autogenerate -m "description"`
