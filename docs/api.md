# Agent Space REST API Reference

Base URL: `/api/v1`

All authenticated endpoints require an `Authorization: Bearer <JWT>` header containing a valid OpenID Connect access token issued by Keycloak or configured OIDC provider.

---

## 1. Authentication & Identity (`/auth`)

### `GET /api/v1/auth/me`
- **Summary**: Returns the authenticated actor's profile, roles, and tenant organization mapping.
- **Auth**: Required (`ORG_ADMIN`, `PROJECT_MAINTAINER`, `PROJECT_MEMBER`, `OBSERVER`).
- **Response**: `200 OK`
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "username": "lead_dev",
  "email": "lead@agentspace.io",
  "role": "ORG_ADMIN",
  "organization_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

### `POST /api/v1/auth/login`
- **Summary**: Verifies a local account password and issues an access token. Admin accounts use the administrator login endpoint.
- **Auth**: Public.
- **Request Body**:
```json
{
  "username": "dev_user",
  "password": "secure_password"
}
```
- **Response**: `200 OK` (`access_token`, `token_type`, `expires_in`, `user`).

### `POST /api/v1/auth/admin/login`
- **Summary**: Verifies the account password, then requires `ORG_ADMIN` or `SYSTEM_ADMIN` role.
- **Auth**: Public sign-in endpoint; password and admin role are required.
- **Request Body**:
```json
{
  "username": "admin_a",
  "password": "secure_admin_password"
}
```
- **Response**: `200 OK` (`access_token`, `token_type`, `expires_in`, `user`).

### `GET /api/v1/auth/admin/session`
- **Summary**: Protected admin verification endpoint guarded by `require_role(Role.ORG_ADMIN)`.
- **Auth**: Required (`ORG_ADMIN`, `SYSTEM_ADMIN`).
- **Response**: `200 OK` (Admin user profile with organization mapping and admin role grants).

### `POST /api/v1/auth/register`
- **Summary**: Registers a new user and a new organization workspace, stores a salted password hash, and issues an access token. Joining an existing workspace requires an administrator-managed flow.
- **Auth**: Public.
- **Request Body**:
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "organization_name": "Acme Robotics",
  "password": "secure_password"
}
```
- **Response**: `201 Created` (`access_token`, `token_type`, `expires_in`, `user`).

### `POST /api/v1/auth/refresh`
- **Summary**: Refreshes expired access token using a valid refresh token.
- **Auth**: Public.
- **Request Body**: `{"refresh_token": "string"}`
- **Response**: `200 OK` (`access_token`, `refresh_token`, `expires_in`).

### `POST /api/v1/auth/logout`
- **Summary**: Invalidates active refresh token and terminates session.
- **Auth**: Required.
- **Request Body**: `{"refresh_token": "string"}`
- **Response**: `204 No Content`

---

## 2. Organizations & Tenants (`/organizations`)

### `POST /api/v1/organizations`
- **Summary**: Creates a new multi-tenant organization.
- **Auth**: Required (`SYSTEM_ADMIN`, `ORG_ADMIN`).
- **Request Body**: `{"name": "Acme Corp", "slug": "acme-corp"}`
- **Response**: `201 Created`

### `GET /api/v1/organizations/{organization_id}`
- **Summary**: Retrieves organization details by ID. Enforces tenant boundary.
- **Auth**: Required (Member of the target organization).
- **Response**: `200 OK`

---

## 3. Projects (`/projects`)

### `GET /api/v1/projects`
- **Summary**: Lists all projects in the caller's organization.
- **Auth**: Required (`PROJECT_READ`).
- **Query Params**: `offset` (default 0), `limit` (default 100).
- **Response**: `200 OK` (Array of ProjectResponse).

### `POST /api/v1/projects`
- **Summary**: Creates a new engineering project within the organization.
- **Auth**: Required (`PROJECT_CREATE`).
- **Request Body**:
```json
{
  "name": "URL Shortener Platform",
  "slug": "url-shortener",
  "description": "Enterprise URL shortener with analytics",
  "repository_url": "https://gitea.local/acme/url-shortener",
  "default_branch": "main"
}
```
- **Response**: `201 Created`

### `GET /api/v1/projects/{project_id}`
- **Summary**: Retrieves a single project by ID.
- **Auth**: Required (`PROJECT_READ`).
- **Response**: `200 OK`

### `PATCH /api/v1/projects/{project_id}`
- **Summary**: Updates project metadata and settings.
- **Auth**: Required (`PROJECT_UPDATE`).
- **Request Body**: `{"name": "string", "description": "string", "status": "ACTIVE"}`
- **Response**: `200 OK`

### `DELETE /api/v1/projects/{project_id}`
- **Summary**: Permanently deletes a project and cascades dependencies.
- **Auth**: Required (`PROJECT_DELETE`).
- **Response**: `204 No Content`

### `GET /api/v1/projects/{project_id}/summary`
- **Summary**: Returns executive summary metrics (member count, task status breakdown).
- **Auth**: Required (`PROJECT_READ`).
- **Response**: `200 OK`

---

## 4. Project Memberships (`/projects/{project_id}/members`)

### `GET /api/v1/projects/{project_id}/members`
- **Summary**: Lists all human and agent members in a project.
- **Auth**: Required (`PROJECT_READ`).
- **Response**: `200 OK`

### `POST /api/v1/projects/{project_id}/members`
- **Summary**: Adds a user or agent to the project with an assigned role.
- **Auth**: Required (`PROJECT_UPDATE`).
- **Request Body**: `{"user_id": "uuid", "role": "DEVELOPER"}`
- **Response**: `201 Created`

### `DELETE /api/v1/projects/{project_id}/members/{user_id}`
- **Summary**: Removes a member from the project.
- **Auth**: Required (`PROJECT_UPDATE`).
- **Response**: `204 No Content`

---

## 5. Tasks & Workflow Lifecycle (`/tasks`, `/projects/{project_id}/tasks`)

### `GET /api/v1/projects/{project_id}/tasks`
- **Summary**: Lists tasks belonging to a project with optional status filter.
- **Auth**: Required (`TASK_READ`).
- **Query Params**: `status`, `offset`, `limit`.
- **Response**: `200 OK`

### `POST /api/v1/projects/{project_id}/tasks`
- **Summary**: Creates a new task within a project.
- **Auth**: Required (`TASK_CREATE`).
- **Request Body**:
```json
{
  "title": "Build URL Shortener API",
  "description": "FastAPI service with base62 encoding",
  "priority": "HIGH"
}
```
- **Response**: `201 Created`

### `GET /api/v1/tasks/{task_id}`
- **Summary**: Fetches task details, context, assigned agent, and current state.
- **Auth**: Required (`TASK_READ`).
- **Response**: `200 OK`

### `PATCH /api/v1/tasks/{task_id}`
- **Summary**: Updates task title, description, priority, or status.
- **Auth**: Required (`TASK_UPDATE`).
- **Response**: `200 OK`

### `DELETE /api/v1/tasks/{task_id}`
- **Summary**: Permanently removes a task.
- **Auth**: Required (`TASK_DELETE`).
- **Response**: `204 No Content`

### `POST /api/v1/tasks/{task_id}/assign`
- **Summary**: Atomically assigns a task to an agent or user with optimistic locking.
- **Auth**: Required (`TASK_ASSIGN`).
- **Request Body**: `{"agent_id": "uuid", "expected_version": 1}`
- **Response**: `200 OK`

### `POST /api/v1/tasks/{task_id}/transition`
- **Summary**: Executes validated state machine transitions (`TODO` -> `IN_PROGRESS` -> `REVIEW` -> `DONE`).
- **Auth**: Required (`TASK_UPDATE`).
- **Request Body**: `{"status": "IN_PROGRESS", "reason": "Starting execution", "expected_version": 1}`
- **Response**: `200 OK`

### `GET /api/v1/tasks/{task_id}/dependencies`
- **Summary**: Lists prerequisite task IDs that must complete before this task can start.
- **Auth**: Required (`TASK_READ`).
- **Response**: `200 OK`

### `POST /api/v1/tasks/{task_id}/dependencies`
- **Summary**: Adds a directed dependency edge. Validates against DAG cycles.
- **Auth**: Required (`TASK_UPDATE`).
- **Request Body**: `{"depends_on_task_id": "uuid"}`
- **Response**: `201 Created`

### `DELETE /api/v1/tasks/{task_id}/dependencies/{dependency_task_id}`
- **Summary**: Removes a dependency prerequisite edge.
- **Auth**: Required (`TASK_UPDATE`).
- **Response**: `204 No Content`

### `POST /api/v1/tasks/{task_id}/takeover`
- **Summary**: Human seizes control of an active task from an agent with row locking and audit logging.
- **Auth**: Required (`TASK_ASSIGN`).
- **Request Body**: `{"reason": "Human manual fix required", "expected_version": 2}`
- **Response**: `200 OK`

### `POST /api/v1/tasks/{task_id}/handoff`
- **Summary**: Hands off task ownership from a human user back to an agent with instructions.
- **Auth**: Required (`TASK_ASSIGN`).
- **Request Body**: `{"agent_id": "uuid", "instructions": "Continue testing after fix"}`
- **Response**: `200 OK`

### `POST /api/v1/tasks/{task_id}/requests`
- **Summary**: Agent durably pauses workflow and requests human decision, approval, or assistance.
- **Auth**: Required (`TASK_UPDATE`).
- **Request Body**:
```json
{
  "request_type": "APPROVAL",
  "prompt": "Review passed. Confirm production deployment.",
  "options": ["APPROVE", "REJECT"],
  "context": {"diff_size": 150}
}
```
- **Response**: `200 OK` (Status updated to `BLOCKED`).

### `POST /api/v1/tasks/{task_id}/requests/respond`
- **Summary**: Human responds to pending agent request, unblocking the task.
- **Auth**: Required (`TASK_UPDATE`).
- **Request Body**: `{"action": "APPROVE", "feedback": "Approved for deploy", "selected_option": "APPROVE"}`
- **Response**: `200 OK` (Status resumed to `IN_PROGRESS`).

### `GET /api/v1/projects/{project_id}/audit-events`
- **Summary**: Retrieves domain audit outbox events for compliance and live activity feeds.
- **Auth**: Required (`TASK_READ`).
- **Response**: `200 OK`

---

## 6. Autonomous Agents (`/agents`)

### `GET /api/v1/agents`
- **Summary**: Lists registered autonomous agents available for assignment.
- **Auth**: Required.
- **Response**: `200 OK`

### `GET /api/v1/agents/model-defaults`
- **Summary**: Returns the default provider, model, endpoint, and free-tier model list offered when adding an agent. Contains no secrets — agent API keys are supplied by the client.
- **Auth**: Required.
- **Response**: `200 OK`

### `POST /api/v1/agents`
- **Summary**: Registers a new agent profile with capabilities and model configuration.
- **Auth**: Required (`ORG_ADMIN`).
- **Response**: `201 Created`

### `GET /api/v1/agents/{agent_id}`
- **Summary**: Fetches agent status, current workload, and capabilities.
- **Auth**: Required.
- **Response**: `200 OK`

### `POST /api/v1/agents/{agent_id}/heartbeat`
- **Summary**: Agent worker sends periodic liveness ping.
- **Auth**: Required (`Agent Worker Token`).
- **Response**: `200 OK`

### `GET /api/v1/agents/roles/match`
- **Summary**: Queries scheduler matcher for best available agent for given capability tags.
- **Auth**: Required.
- **Query Params**: `role`, `capabilities`.
- **Response**: `200 OK`

---

## 7. Realtime Gateway (`/ws/projects/{project_id}`)

### `WS /api/v1/ws/projects/{project_id}`
- **Summary**: Real-time WebSocket event subscription for collaborative UI.
- **Auth**: Validated via ticket / query token before socket connection accepted.
- **Dispatches Events**:
  - `task.updated`
  - `task.assigned`
  - `task.released`
  - `agent.status`
  - `artifact.created`
  - `workflow.updated`
  - `human.input_required`

---

## 8. System Health & Operator Telemetry

### `GET /health` or `GET /api/v1/health`
- **Summary**: Overall composite system health check.
- **Auth**: Public.
- **Response**: `200 OK`

### `GET /health/liveness` or `GET /api/v1/health/liveness`
- **Summary**: Kubernetes liveness probe endpoint (process running).
- **Auth**: Public.
- **Response**: `200 OK`

### `GET /health/readiness` or `GET /api/v1/health/readiness`
- **Summary**: Kubernetes readiness probe verifying PostgreSQL, Redis, and Temporal connectivity.
- **Auth**: Public.
- **Response**: `200 OK`

### `GET /api/v1/operator/stats`
- **Summary**: Real-time telemetry: active connections, workflow queue depth, memory and database pool stats.
- **Auth**: Required (`SYSTEM_ADMIN`, `ORG_ADMIN`).
- **Response**: `200 OK`
