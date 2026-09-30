# Agent Space System Service Catalog

Comprehensive inventory of all platform services, network ports, health checks, and storage requirements.

---

## Service Matrix

| Service | Component | Default Port | Protocol | Container Image | Healthcheck Endpoint | Primary Storage |
|---|---|---|---|---|---|---|
| `backend` | Core API | 8000 | HTTP/WS | `agentspace/backend:latest` | `GET /health/readiness` | Stateless (DB-backed) |
| `worker` | Workflow Runner | N/A | Daemon | `agentspace/worker:latest` | Temporal Heartbeat | Stateless (DB-backed) |
| `frontend` | Next.js UI | 3000 | HTTP | `agentspace/frontend:latest` | `GET /api/health` | Stateless |
| `postgres` | Primary DB | 5432 | TCP (pg) | `postgres:16-alpine` | `pg_isready -U postgres` | Persistent Volume (WAL) |
| `redis` | Cache & Locks | 6379 | TCP (resp)| `redis:7-alpine` | `redis-cli ping` | Ephemeral / AOF |
| `nats` | Event Bus | 4222 | TCP | `nats:2.10-alpine` | `GET /varz` | JetStream Storage |
| `temporal` | Orchestrator | 7233 | gRPC | `temporalio/auto-setup:1.24`| `temporal cluster health` | PostgreSQL backing |
| `temporal-ui`| Workflow UI | 8233 | HTTP | `temporalio/ui:2.26` | `GET /` | Stateless |
| `keycloak` | OIDC Identity | 8080 | HTTP | `quay.io/keycloak/keycloak:24`| `GET /health/ready` | PostgreSQL backing |
| `gitea` | Git Host | 3001 / 2222 | HTTP / SSH | `gitea/gitea:1.22-rootless`| `GET /api/v1/version` | Git Bare Repositories |
| `seaweedfs` / `minio` | CAS Artifacts | 9000 / 9001 | HTTP / S3 | `minio/minio:RELEASE...` | `GET /minio/health/live` | Immutable Object Volume |
| `qdrant` | Vector Memory | 6333 | HTTP/gRPC | `qdrant/qdrant:v1.9` | `GET /healthz` | HNSW Vector Index |
| `otel-collector` | Telemetry | 4317 / 4318 | gRPC / HTTP | `otel/opentelemetry-collector-contrib` | `GET /health` | In-memory Buffer |
| `prometheus` | Metrics Engine | 9090 | HTTP | `prom/prometheus:v2.52` | `GET /-/healthy` | TSDB Time-series |
| `alertmanager` | Alert Router | 9093 | HTTP | `prom/alertmanager:v0.27` | `GET /-/healthy` | In-memory / State |
| `grafana` | Dashboards | 3002 | HTTP | `grafana/grafana:11.0` | `GET /api/health` | SQLite / Postgres |
| `loki` | Log Aggregator | 3100 | HTTP | `grafana/loki:3.0` | `GET /ready` | Filesystem Object Store |

---

## Detailed Service Specifications

### 1. `backend`
- **Role**: Primary API gateway handling REST requests, OIDC auth checks, and WebSockets.
- **Resources**: 512MB RAM minimum, 2048MB RAM limit; 0.5 CPU requests, 2.0 CPU limits.
- **Failure Mode**: Auto-restarts; cluster ingress redirects to surviving replica pods.

### 2. `worker`
- **Role**: Asynchronous execution loop consuming Temporal queues and driving agent cognitive loops.
- **Resources**: 1024MB RAM minimum, 4096MB RAM limit; 1.0 CPU requests, 4.0 CPU limits.
- **Failure Mode**: Temporal reassigns in-flight activities if heartbeats cease.

### 3. `postgres`
- **Role**: Authoritative ACID relational data store for all persistent models.
- **Resources**: 2048MB RAM minimum, 8192MB RAM limit; 1.0 CPU requests, 4.0 CPU limits.
- **High Availability**: Managed RDS / Azure Flexible Server in cloud deployments.
