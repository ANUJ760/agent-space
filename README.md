# Agent Space

> A modular, self-hostable collaboration platform where human engineering teams and autonomous AI agents collaborate on software and complex projects.

---

## 1. Overview

**Agent Space** is not another chatbot wrapper or standalone prompt playground. It is an **operating system for human + agent work**.

It provides:
- **Multi-Tenant Collaboration**: Organizations, projects, role-based access control (RBAC), and team members.
- **Human & Agent Parity**: AI agents act as full team members capable of being assigned tasks, collaborating on Git repositories, raising review requests, and handing off execution.
- **Durable Workflow Execution**: Powered by Temporal for orchestrating resilient, long-running agent loops that survive restarts and failures.
- **Strict Concurrency Guarantees**: PostgreSQL row-level locks, optimistic versioning, idempotency keys, and transactional outboxes.
- **Sandboxed Agent Tools**: Isolated Docker / gVisor environments with network and resource governance.
- **Shared Project Memory**: Semantic vector search via Qdrant for project history, decisions, and codebase context.
- **Realtime Collaboration**: Bidirectional WebSockets backed by NATS JetStream and Redis.

---

## 2. Global Architecture

```text
                         ┌─────────────────────────┐
                         │       Next.js UI        │
                         │ TS + Tailwind + shadcn  │
                         └────────────┬────────────┘
                                      │ HTTPS / WS
                                      ▼
                         ┌─────────────────────────┐
                         │        FastAPI          │
                         │ API + Auth + Services   │
                         └──────┬─────────┬────────┘
                                │         │
                                ▼         ▼
                         PostgreSQL      Redis
                         truth/state     cache/ephemeral
                                │
                                ▼
                         ┌──────────────┐
                         │   NATS       │
                         │  JetStream   │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   Temporal   │
                         │   Workflows  │
                         └──────┬───────┘
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                    Agent Workers   Tool Gateway
                         │             │
                         ▼             ▼
                    LangGraph       Sandbox
                         │        Docker/gVisor
                         ▼
                    Model Gateway
                    Ollama/vLLM

               ┌────────────┬────────────┬────────────┐
               ▼            ▼            ▼            ▼
             Qdrant      SeaweedFS     Gitea      Keycloak
             memory      artifacts      Git        identity
```

### Core Architecture Invariants

- **PostgreSQL**: Authoritative single source of truth for all application state.
- **Temporal**: Durable workflow execution engine; eliminates fragile long-running HTTP connections.
- **LangGraph**: Cognitive agent reasoning graphs and tool decision loops.
- **NATS JetStream**: High-throughput distributed event bus.
- **WebSocket**: Live updates and real-time multiplayer feeds to browser clients.
- **Redis**: Ephemeral presence, fast caching, and session tracking.
- **Qdrant**: High-performance semantic vector database for project memory.
- **Gitea**: Dedicated Git server managing isolated branches and worktrees per agent.
- **SeaweedFS / S3**: Immutable object storage for artifacts, patches, and logs.
- **Keycloak**: OpenID Connect / OAuth2 identity and authorization server.
- **Tool Gateway**: Authorization and validation boundary for all agent capabilities.
- **Sandbox (Docker / gVisor)**: Untrusted code and command execution barrier.

---

## 3. Repository Structure

```text
agent-space/
├── apps/
│   ├── backend/         # FastAPI REST API, auth, and database services
│   └── frontend/        # Next.js collaborative UI
├── agents/              # Autonomous agent graphs (Coding, Research, Testing, Review, Vision)
├── packages/            # Shared Python and TypeScript libraries, schemas, DB models
├── infrastructure/      # Docker Compose, Kubernetes manifests, OpenTofu scripts
├── docs/                # Architecture specifications, API documentation, runbooks
├── tests/               # Test suites (Unit, Integration, Concurrency, Temporal, E2E)
├── README.md            # Project overview and onboarding
├── LICENSE              # Apache 2.0 open-source license
├── .gitignore           # Git ignore rules for build artifacts and environments
├── .dockerignore        # Container build exclude rules
├── .env.example         # Centralized configuration reference
├── pyproject.toml       # Python packaging, dependency, and tool settings
├── package.json         # Node workspace configuration
└── Makefile             # Developer automation commands
```

---

## 4. Getting Started

### Prerequisites

- **Python**: `>= 3.11`
- **Node.js**: `>= 20.0` and **npm**: `>= 10.0`
- **Docker & Docker Compose**: for local services

### Environment Setup

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Adjust configuration parameters in `.env` as required for your local setup.
   > **Detailed Walkthrough**: See [`docs/setup_guide.md`](docs/setup_guide.md) for production placeholder values, database seeding, credentials matrix, and 3-tab workspace instructions.

### Development Commands

Agent Space includes a top-level `Makefile` for developer workflow:

```bash
# Display available commands
make help

# Run test suite
make test

# Run code linters (Ruff & Mypy)
make lint

# Automatically format code
make format

# Run full verification check (lint + test)
make check

# Clean temporary caches and build artifacts
make clean
```

---

## 5. Modular Build Plan & Execution Gates

Agent Space follows a strict **modular execution model**: each module is implemented independently, verified through automated tests, and gated by human review before proceeding to the next.

1. **Foundation**: `M00` (Repo Contract) → `M01` (Config) → `M02` (FastAPI) → `M03` (Postgres) → `M04` (Alembic) → `M05` (Health)
2. **Auth & RBAC**: `M06` (Keycloak) → `M07` (Users/Orgs) → `M08` (RBAC)
3. **Core Application**: `M09` (Projects) → `M10` (Members) → `M11` (Agent Registry) → `M12` (Tasks) → `M13` (State Machine) → `M14` (Dependencies) → `M15` (Assignment)
4. **Concurrency**: `M16` (Optimistic Locking) → `M17` (Row Locks) → `M18` (Idempotency) → `M19` (Transactional Outbox)
5. **Frontend**: `M20` (Next.js Shell) → `M21` (Auth UI) → `M22` (Dashboard) → `M23` (Project UI) → `M24` (Kanban UI)
6. **Realtime & Messaging**: `M25` (Redis) → `M26` (NATS JetStream) → `M27` (WebSocket Gateway)
7. **Workflows**: `M28` (Temporal Client) → `M29` (Worker Infra) → `M30` (TaskWorkflow) → `M31` (Signals) → `M32` (Recovery)
8. **Agents & Tools**: `M33` - `M46` (Agent Protocols, LangGraph Runtime, Coding/Review/Testing/Vision Agents, Tool Gateway, Sandbox Isolation)
9. **Git, Storage & Memory**: `M47` - `M52` (Gitea, Workspaces, Artifacts, Qdrant)
10. **Human-in-the-Loop Collaboration**: `M53` - `M57` (Takeover, Handoff, Activity Feed, Progress)
11. **Scheduling & DAG**: `M58` - `M61` (Capability Matching, Task DAG Execution, Scheduling Explainability)
12. **Security, Observability & Verification**: `M62` - `M90` (Audits, OpenTelemetry, Prometheus, Full Test Suites, Deployment)

---

## 6. License

This project is licensed under the [Apache 2.0 License](LICENSE).
