# Agent Space — Global Architecture & Engineering Invariants

## 1. System Overview

**Agent Space** is a modular, self-hostable collaboration platform where human teams and autonomous AI agents collaborate on software engineering and operational workflows.

Rather than treating AI agents as simple chatbots or stateless request-response helpers, Agent Space provides an **operating system for human + agent work**. It manages projects, tasks, dependency DAGs, durable long-running workflows, sandboxed tool executions, multi-tenant RBAC, live activity streaming, and concurrent Git branch manipulation.

---

## 2. Global Architecture Diagram

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

---

## 3. Architecture Invariants

These invariants must be preserved across every module and feature:

| Component | Responsibility / Invariant |
|---|---|
| **PostgreSQL** | Authoritative application state and single source of truth |
| **Temporal** | Durable, fault-tolerant workflow execution for long-running processes |
| **LangGraph** | Agent reasoning, tool invocation graph, and cycle execution |
| **NATS JetStream** | Scalable, decoupled domain event transport |
| **WebSocket** | Realtime bidirectional event delivery to connected web clients |
| **Redis** | Ephemeral state, presence tracking, and caching |
| **Qdrant** | Semantic vector memory for agents and project context |
| **Git (Gitea)** | Source code isolation and concurrency (branches & worktrees) |
| **Object Storage (SeaweedFS / S3)** | Immutable storage for large build artifacts, diffs, and logs |
| **Keycloak** | Centralized identity, OpenID Connect, OAuth2, and token issuance |
| **Tool Gateway** | Agent capability boundary and tool invocation authorization |
| **Sandbox (Docker / gVisor)** | Untrusted code and command execution isolation boundary |

---

## 4. Concurrency Architecture

Concurrent interactions between multiple humans and autonomous agents require strict consistency guarantees:

```text
                 ┌──────────────────┐
                 │    PostgreSQL    │
                 │                  │
                 │ optimistic lock │
                 │ row locks       │
                 │ transactions    │
                 └────────┬─────────┘
                          │
                     authoritative
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   Task State         Assignment         Outbox
        │                 │                 │
        │                 │                 ▼
        │                 │              NATS
        │                 │                 │
        │                 │                 ▼
        ▼                 ▼             WebSockets
     Temporal        Human takeover
        │
        ▼
     Workers
        │
        ▼
   Git workspaces
        │
        ▼
    Merge/review
```

### Concurrency Mechanisms:
1. **Optimistic Version Locking**: Prevents lost updates on task state updates (`version` integer incremented on every update; fails with `TASK_VERSION_CONFLICT` if mismatched).
2. **PostgreSQL Row-Level Locks (`SELECT FOR UPDATE`)**: Eliminates race conditions during task assignment, human takeover, and state transitions.
3. **Idempotency Keys**: Guarantees that retried mutation requests produce the exact same outcome without duplicate side-effects.
4. **Transactional Outbox**: Ensures database state transitions and NATS domain events are atomically committed together.
5. **Git Worktree Isolation**: Each agent task operates on an isolated Git worktree/branch to avoid working tree contention.

---

## 5. Security Architecture & Boundaries

Agent Space enforces 8 explicit security perimeters:

```text
Browser
  ↓ TLS
Keycloak (OIDC Authentication)
  ↓ JWT validation
FastAPI (Tenant & Project RBAC Authorization)
  ↓
Temporal Workflow Engine
  ↓
Agent Workers
  ↓ Capability verification
Tool Gateway (Policy & Parameter Authorization)
  ↓
Sandbox (Isolated Container / gVisor)
  ↓
Host / Network Boundary
```

1. **Identity Boundary**: Keycloak manages identities, passwords, MFA, and OAuth2 tokens.
2. **Tenant Boundary**: Strict organization-level data segregation across all queries.
3. **Project Authorization Boundary**: Role-based access control (Admin, Member, Viewer, Agent) per project.
4. **Agent Capability Boundary**: Agents are only permitted to execute tools registered in their capability manifest.
5. **Tool Authorization Boundary**: Every tool invocation is inspected, authenticated, and logged before dispatch.
6. **Sandbox Boundary**: Agent-generated shell commands and scripts run exclusively inside containerized sandboxes with restricted syscalls.
7. **Network Boundary**: Outbound network access from execution sandboxes is disabled or strictly allowlisted.
8. **Artifact Boundary**: Presigned URLs and scoped permissions govern access to generated artifacts and logs.

---

## 6. Monorepo Structure

```text
agent-space/
├── apps/
│   ├── backend/         # FastAPI application, REST APIs, and database services
│   └── frontend/        # Next.js, Tailwind, shadcn/ui collaborative dashboard
├── agents/              # Agent reasoning graphs (Coding, Research, Testing, Review, Vision)
├── packages/            # Shared libraries, schemas, DB models, and utilities
├── infrastructure/      # Docker Compose, Kubernetes manifests, OpenTofu scripts
├── docs/                # Architecture specifications, API documentation, runbooks
├── tests/               # Unit, integration, concurrency, and end-to-end test suites
├── README.md            # Project overview and developer onboarding
├── LICENSE              # Apache 2.0 open-source license
├── .gitignore           # Git ignore rules for build artifacts and environments
├── .dockerignore        # Container packaging exclude rules
├── .env.example         # Centralized configuration reference
├── pyproject.toml       # Python packaging, dependency, and tool settings
├── package.json         # Node workspace configuration
└── Makefile             # Developer automation commands
```
