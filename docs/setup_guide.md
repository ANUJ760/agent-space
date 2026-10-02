# Agent Space — Complete Platform Setup & Operations Guide

This comprehensive guide details the complete end-to-end setup, environment configuration, database seeding, running, and testing instructions for **Agent Space** across local development and production environments.

---

## Table of Contents

1. [Architecture & System Prerequisites](#1-architecture--system-prerequisites)
2. [Environment Configuration & Production Placeholders](#2-environment-configuration--production-placeholders)
3. [Infrastructure Provisioning (Database & Redis)](#3-infrastructure-provisioning-database--redis)
4. [Database Migrations & Seeding](#4-database-migrations--seeding)
5. [Seeded Credentials & Access Matrix](#5-seeded-credentials--access-matrix)
6. [Starting the Application Services](#6-starting-the-application-services)
7. [Frontend Architecture & Key UI Features](#7-frontend-architecture--key-ui-features)
8. [Testing & Quality Verification](#8-testing--quality-verification)
9. [Stopping & Service Teardown](#9-stopping--service-teardown)
10. [Troubleshooting Common Issues](#10-troubleshooting-common-issues)

---

## 1. Architecture & System Prerequisites

### Required Runtimes & Tools

| Component | Minimum Version | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **Linux / macOS / WSL2** | Ubuntu 22.04+ / macOS 13+ | Fedora 40+ / Ubuntu 24.04 | Standard POSIX shell environment |
| **Python** | `3.11+` | `3.12` or `3.13` | Backend API & Worker runtime |
| **Node.js** | `v20.0.0+` | `v20.14.0+` (LTS) | Frontend Next.js 14 runtime |
| **npm** | `v10.0.0+` | `v10.8.0+` | Monorepo package management |
| **Podman / Docker** | `v4.0.0+` / `v24.0.0+` | Rootless Podman or Docker Compose | Containerized stateful services |

### Network Port Allocation

| Port | Service | Protocol | Description |
| :--- | :--- | :--- | :--- |
| **`3000`** | Next.js Frontend | HTTP | Web UI, Three.js 3D animations, Workspace |
| **`8000`** | FastAPI Backend | HTTP / REST | OpenAPI docs, REST endpoints, WebSocket pub/sub |
| **`5432`** | PostgreSQL 16 | TCP | Relational store, row-level locks, audit log |
| **`6379`** | Redis 7 | TCP | State cache, task lease locks, real-time events |
| **`8080`** | Keycloak *(Optional/Prod)* | HTTP | Production OIDC / SSO identity provider |
| **`7233`** | Temporal *(Optional/Prod)*| gRPC | Long-running multi-agent workflow orchestration |

---

## 2. Environment Configuration & Production Placeholders

Agent Space uses environment variables managed through `.env` in the repository root.

### Initializing `.env`

```bash
cp .env.example .env
```

### Critical Placeholders Requiring Configuration for Production

When transitioning from local development to production, update these values in `.env`:

```env
# ==============================================================================
# 1. CORE ENVIRONMENT & SECURITY SECRETS
# ==============================================================================
ENVIRONMENT=production                 # Change from 'development' to 'production'
LOG_LEVEL=INFO                         # Set to 'INFO' or 'WARNING' in production

# Generate with: openssl rand -hex 32
SECRET_KEY=change_this_to_a_secure_random_64_character_hex_string_in_production

# ==============================================================================
# 2. DATABASE (PostgreSQL 16)
# ==============================================================================
# Production format: postgresql+asyncpg://<db_user>:<db_password>@<db_host>:<db_port>/<db_name>
DATABASE_URL=postgresql+asyncpg://agentspace_prod_user:SuperSecureProdPassword123!@postgres.internal.net:5432/agentspace_prod
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# ==============================================================================
# 3. REDIS DISTRIBUTED CACHE & LEASES
# ==============================================================================
# Production format: rediss://:<password>@<redis_host>:6379/0 (use 'rediss://' for TLS)
REDIS_URL=redis://:RedisSecurePassword123!@redis.internal.net:6379/0

# ==============================================================================
# 4. IDENTITY PROVIDER / OIDC (Keycloak / Okta / Azure AD)
# ==============================================================================
OIDC_ISSUER_URL=https://auth.yourdomain.com/realms/agentspace
OIDC_CLIENT_ID=agentspace-backend
OIDC_CLIENT_SECRET=change_this_to_your_keycloak_client_secret
OIDC_JWKS_URL=https://auth.yourdomain.com/realms/agentspace/protocol/openid-connect/certs

# ==============================================================================
# 5. DEFAULT AGENT AND PLANNER (server-side Gemini key)
# ==============================================================================
DEFAULT_GEMINI_API_KEY=your_gemini_api_key_here
DEFAULT_AGENT_MODEL=gemini-2.5-flash

# ==============================================================================
# 6. CORS & PUBLIC DOMAINS
# ==============================================================================
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
CORS_ORIGINS=["https://app.yourdomain.com","https://admin.yourdomain.com"]
```

Users add their own OpenAI, Anthropic, or other provider keys in the application's agent settings. Those keys are kept in the browser and are not server environment variables.

---

## 3. Infrastructure Provisioning (Database & Redis)

Start PostgreSQL 16 and Redis 7 containers locally using Podman or Docker:

### Using Podman (Rootless):

```bash
# Start PostgreSQL 16
podman run -d --name agentspace-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=agentspace \
  -p 5432:5432 \
  postgres:16-alpine

# Start Redis 7
podman run -d --name agentspace-redis \
  -p 6379:6379 \
  redis:7-alpine
```

### Using Docker Compose:

```bash
docker compose up -d postgres redis
```

---

## 4. Database Migrations & Seeding

### Step 1: Run Alembic Migrations

Ensure all database tables, foreign keys, version columns, and indexes are created:

```bash
PYTHONPATH=apps/backend python3 -m alembic upgrade head
```

### Step 2: Run the Seeding Script

Agent Space includes an idempotent database seeding script ([`scripts/seed_database.py`](file:///home/anuj/Downloads/AgentSpace/scripts/seed_database.py)) that provisions the default organization, RBAC user personas, initial project, autonomous agents, and sample milestone tasks:

```bash
PYTHONPATH=apps/backend python3 scripts/seed_database.py
```

Expected output:
```text
Database connected. Beginning idempotent seeding...
[EXISTS]  Organization: Acme Corporation (acme-corp)
[EXISTS]  User: admin (Role: ORG_ADMIN, Email: admin@agentspace.local)
[EXISTS]  User: lead (Role: PROJECT_OWNER, Email: lead@agentspace.local)
[EXISTS]  User: developer (Role: MEMBER, Email: developer@agentspace.local)
[EXISTS]  User: auditor (Role: VIEWER, Email: auditor@agentspace.local)
[EXISTS]  Project: Platform Engineering (platform-engineering)
[CREATED] Agent: DevOps-Agent-01 (devops-agent-01)
[CREATED] ProjectMember: lead as OWNER
[CREATED] ProjectMember: developer as MEMBER
[CREATED] ProjectMember: auditor as VIEWER
[CREATED] Task: Architecture Specification & Threat Modeling (Status: DONE)
[CREATED] Task: Multi-Cloud Kubernetes Ingress Setup (Status: DONE)
[CREATED] Task: Autonomous CI/CD Deployment Pipeline (Status: IN_PROGRESS)
[CREATED] Task: Distributed State Synchronization & Cache Warmup (Status: IN_PROGRESS)
[CREATED] Task: Zero-Trust Service Mesh Verification (Status: TODO)
Seeding finished successfully.
```

---

## 5. Seeded Credentials & Access Matrix

### 1. Dedicated Protected Admin Portal
- **Frontend Portal URL**: `http://localhost:3000/admin/login`
- **Backend Protected Endpoint**: `POST /api/v1/auth/admin/login`
- **Verification Endpoint**: `GET /api/v1/auth/admin/session`

| Username | Role | Description |
| :--- | :--- | :--- |
| **`admin`** | `ORG_ADMIN` | Organization administrator; set a private password before use |

> [!IMPORTANT]
> **Strict Admin Isolation**: The `/admin/login` page has **zero signup options**. Standard member accounts cannot authenticate here, and admin accounts are strictly rejected with `403 Forbidden` if attempting to log in via the standard `/login` route.

---

### 2. Standard Workspace Members
- **Frontend Portal URL**: `http://localhost:3000/login`
- **Backend Endpoint**: `POST /api/v1/auth/login`

| Username | Role | Capabilities |
| :--- | :--- | :--- |
| **`lead`** | `PROJECT_OWNER` | Manage projects, assign tasks to agents, approve PRs |
| **`developer`** | `MEMBER` | Execute claimed tasks, pair program with AI agents |
| **`auditor`** | `VIEWER` | Read-only inspection of audit events and outbox logs |

Seeded accounts have no preset passwords. After migrations, run
`PYTHONPATH=apps/backend:. python3 scripts/set_user_password.py admin` (or another
username) and enter a private password at the prompt. Existing accounts created
before password hashing need the same one-time setup.

---

### 3. Seeded Autonomous AI Agents

| Agent Name | Slug | Role | Model Provider | Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **DevOps-Agent-01** | `devops-agent-01` | `DEVOPS_ENGINEER` | Anthropic `claude-3-5-sonnet` | `ci_cd`, `code_review`, `container_orchestration`, `security_scanning` |

---

## 6. Starting the Application Services

### Terminal 1: Backend API (FastAPI + Uvicorn)

```bash
# In repository root
PYTHONPATH=apps/backend:. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Verify Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Verify API Liveness: `curl http://localhost:8000/api/v1/health/live`

### Terminal 2: Frontend Web App (Next.js 14)

```bash
# In repository root
npm run dev --workspace=@agent-space/frontend
```

- Access Web App: [http://localhost:3000](http://localhost:3000)
- Member Login: [http://localhost:3000/login](http://localhost:3000/login)
- Protected Admin Portal: [http://localhost:3000/admin/login](http://localhost:3000/admin/login)
- Workspace Projects: [http://localhost:3000/projects](http://localhost:3000/projects)

---

## 7. Frontend Architecture & Key UI Features

### 1. Cybernetic Obsidian Dark Theme
- Base background: Deep obsidian (`--background: 240 12% 4%`, `#09090c`).
- Interior workspace cards feature sharp borders (`rounded-none`, `--radius: 0px`) for high-density technical dashboards.
- Slim navbar and sidebar (`h-11`) with circular minimalist icons and active border indicators.
- **Zero backend leaks**: All mentions of underlying libraries (FastAPI, PostgreSQL, SQLAlchemy, Uvicorn, Keycloak) have been eliminated from the UI.

### 2. High-Contrast Curved Auth Pages
- Main auth containers on `/login` and `/admin/login` feature modern curved corners (`rounded-[32px]`), frosted glassmorphism (`backdrop-blur-2xl bg-zinc-950/90`), and ambient electric glow shadows.
- Generous breathing space (`p-8 sm:p-12`, `max-w-xl`), curved inputs (`rounded-2xl`), and pill-shaped mode toggles (`rounded-full`).

### 3. Three.js 3D Interactive Animations
- **[`AuthThreeAnimation.tsx`](file:///home/anuj/Downloads/AgentSpace/apps/frontend/src/components/canvas/AuthThreeAnimation.tsx)**: Embedded directly into auth headers. Renders an interactive 3D collaboration core with a rotating wireframe icosahedron, a pulsing inner jewel, and dual orbital rings:
  - **Neon Cyan Nodes**: Represent human engineers.
  - **Electric Violet Nodes**: Represent autonomous AI agents.
  - **Vivid Gold Shield**: Represents the privileged Admin Gateway.
  - Cursor tracking tilts the 3D model with smooth easing physics.
- **[`ThreeTransitionCanvas.tsx`](file:///home/anuj/Downloads/AgentSpace/apps/frontend/src/components/canvas/ThreeTransitionCanvas.tsx)**: Ambient background constellation with wave acceleration triggered on route changes.

### 4. 3-Tab Project Workspace
Navigating to [`/projects/[projectId]`](http://localhost:3000/projects/f07df23a-b274-4c13-9851-91c8eacae3f9) presents three dedicated views:
- **Tab 1: Collaborators (Team & AI Roster)**: Side-by-side view of active human software engineers and autonomous AI agents.
- **Tab 2: Progress (Timeline & Milestones — Middle Tab)**: Live sprint completion bar and sequential pipeline with color-coded circular timeline markers:
  - **Cyan Marker (`UserCheck`)**: Human-executed tasks.
  - **Violet Marker (`Bot`)**: Autonomous AI agent-executed tasks.
- **Tab 3: Deliverables (Tasks & Filters)**: Filterable board organized by status (`TODO`, `IN_PROGRESS`, `REVIEW`, `DONE`).

---

## 8. Testing & Quality Verification

Run the complete test suite to ensure 100% operational integrity:

### Backend Tests (`pytest`):
```bash
# Run all 553 backend test cases
python3 -m pytest

# Run auth and RBAC isolation tests specifically
python3 -m pytest tests/test_auth.py tests/test_rbac.py
```
*Expected: 553 passed in ~35s.*

### Frontend Tests (`vitest`):
```bash
npm run test --workspace=@agent-space/frontend
```
*Expected: 25 passed across 6 test suites.*

### Frontend TypeScript Compilation (`tsc`):
```bash
npm run type-check --workspace=@agent-space/frontend
```
*Expected: 0 errors.*

---

## 9. Stopping & Service Teardown

To shut down all running servers and containers:

```bash
# 1. Stop backend Uvicorn processes
pkill -f "uvicorn app.main:app"

# 2. Stop frontend Next.js dev server
pkill -f "next dev"

# 3. Stop background database containers (Podman)
podman stop agentspace-postgres agentspace-redis

# Or if using Docker Compose:
# docker compose down
```

Verify that all ports are released:
```bash
ss -tulpn | grep -E "(3000|8000|5432|6379)"
# (Should return zero listening processes)
```

---

## 10. Troubleshooting Common Issues

### Issue: "403 Access Denied" on `/admin/login`
- **Cause**: Trying to log in with a non-admin account (e.g. `developer`).
- **Fix**: The Admin Portal requires `ORG_ADMIN` or `SYSTEM_ADMIN` role and the account's private password.

### Issue: "Administrator accounts are strictly restricted to the protected Admin Portal" on `/login`
- **Cause**: Attempting to authenticate as `admin` on the standard member login page.
- **Fix**: Open [http://localhost:3000/admin/login](http://localhost:3000/admin/login) to authenticate administrator credentials.

### Issue: PostgreSQL connection refused on port 5432
- **Cause**: Database container is stopped.
- **Fix**: Start the container with `podman start agentspace-postgres` or `docker compose up -d postgres`.
