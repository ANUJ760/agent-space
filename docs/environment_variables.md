# Agent Space Configuration & Environment Variables

All settings can be specified via environment variables or a `.env` file loaded at application startup.

---

## 1. Core Platform Settings

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `ENVIRONMENT` | string | `development` | Yes | Runtime environment (`development`, `staging`, `production`, `test`). |
| `DEBUG` | boolean | `true` | Yes (set `false`) | Enables detailed exception traces and debug mode. |
| `APP_NAME` | string | `Agent Space` | No | Human-readable platform name. |
| `APP_VERSION` | string | `0.1.0` | No | Semantic platform version. |
| `API_V1_PREFIX` | string | `/api/v1` | No | Base routing prefix for v1 API. |
| `SECRET_KEY` | string (secret) | *placeholder* | Yes | 32-byte cryptographic signing key for session security. |
| `HOST` | string | `0.0.0.0` | No | Bind network interface. |
| `PORT` | integer | `8000` | No | HTTP listening port. |
| `CORS_ORIGINS` | json array | `["http://localhost:3000"]` | Yes | Allowed CORS origin headers for web clients. |

---

## 2. PostgreSQL Database (`DATABASE_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `DATABASE_URL` | string | `postgresql+asyncpg://...` | Yes | Async SQLAlchemy connection URI. |
| `DATABASE_POOL_SIZE` | integer | `20` | No | Number of persistent connection sockets in the pool. |
| `DATABASE_MAX_OVERFLOW` | integer | `10` | No | Max temporary burst connections beyond pool size. |
| `DATABASE_POOL_TIMEOUT` | integer | `30` | No | Seconds to wait before failing on pool exhaustion. |
| `DATABASE_ECHO` | boolean | `false` | No | Emits raw SQL queries to stdout for local debugging. |

---

## 3. Redis Ephemeral Cache & Presence (`REDIS_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `REDIS_URL` | string | `redis://localhost:6379/0`| Yes | Connection URI for caching and locks. |
| `REDIS_POOL_SIZE` | integer | `10` | No | Connection pool size for async redis clients. |
| `REDIS_TIMEOUT` | integer | `5` | No | Socket read/write timeout in seconds. |

---

## 4. NATS JetStream Event Messaging (`NATS_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `NATS_URL` | string | `nats://localhost:4222` | Yes | NATS cluster connection URI. |
| `NATS_STREAM_NAME` | string | `AGENT_SPACE_EVENTS` | No | Dedicated JetStream stream identifier. |
| `NATS_CONSUMER_GROUP` | string | `agentspace-backend` | No | Durable consumer group name. |

---

## 5. Temporal Durable Workflows (`TEMPORAL_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `TEMPORAL_HOST` | string | `localhost:7233` | Yes | Temporal gRPC cluster frontend host and port. |
| `TEMPORAL_NAMESPACE` | string | `default` | Yes | Isolated Temporal namespace. |
| `TEMPORAL_TASK_QUEUE` | string | `agent-space-tasks` | No | Default task queue polled by worker pods. |

---

## 6. Keycloak OpenID Connect (`KEYCLOAK_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `KEYCLOAK_SERVER_URL` | string | `http://localhost:8080` | Yes | Base URL of Keycloak instance. |
| `KEYCLOAK_REALM` | string | `agentspace` | Yes | Identity realm name. |
| `KEYCLOAK_CLIENT_ID` | string | `agentspace-backend` | Yes | Backend OAuth2 client identifier. |
| `KEYCLOAK_CLIENT_SECRET` | string (secret) | *placeholder* | Yes | Backend client secret for token verification. |
| `KEYCLOAK_AUDIENCE` | string | `agentspace-backend` | No | Expected audience (`aud`) in access tokens. |

---

## 7. Qdrant Vector Memory (`QDRANT_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `QDRANT_URL` | string | `http://localhost:6333` | Yes | Qdrant vector database HTTP endpoint. |
| `QDRANT_API_KEY` | string (secret) | `null` | Yes (in Cloud) | Optional authentication API key. |
| `QDRANT_COLLECTION` | string | `agent_space_memory` | No | Vector collection name for project context. |

---

## 8. Artifact & Blob Storage (`STORAGE_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `STORAGE_PROVIDER` | string | `s3_compatible` | Yes | Storage driver: `s3_compatible`, `s3`, `azure`, `local`. |
| `STORAGE_ENDPOINT` | string | `http://localhost:8333` | Yes | S3 endpoint URL (SeaweedFS, MinIO, or AWS S3). |
| `STORAGE_BUCKET` | string | `agent-artifacts` | Yes | Destination bucket name. |
| `STORAGE_ACCESS_KEY` | string | `seaweedfs-access` | Yes | S3 Access Key ID. |
| `STORAGE_SECRET_KEY` | string (secret) | *placeholder* | Yes | S3 Secret Access Key. |
| `STORAGE_REGION` | string | `us-east-1` | No | Bucket AWS region. |
| `STORAGE_USE_SSL` | boolean | `false` | Yes (in Prod) | Enforce TLS HTTPS connections. |

---

## 9. Gitea Workspace (`GITEA_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `GITEA_URL` | string | `http://localhost:3001` | Yes | Gitea server HTTP URL. |
| `GITEA_ADMIN_USER` | string | `gitea_admin` | Yes | Admin username for repository management. |
| `GITEA_ADMIN_TOKEN` | string (secret) | *placeholder* | Yes | API token with repository management scope. |

---

## 10. Model Gateway & LLM (`MODEL_GATEWAY_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `MODEL_GATEWAY_PROVIDER` | string | `ollama` | Yes | Provider backend: `ollama`, `vllm`, `openai_compatible`. |
| `MODEL_GATEWAY_BASE_URL` | string | `http://localhost:11434`| Yes | HTTP inference endpoint. |
| `MODEL_GATEWAY_API_KEY` | string (secret) | `null` | Optional | API token for hosted model gateways. |
| `DEFAULT_CHAT_MODEL` | string | `llama3.1:8b` | No | Default conversational model identifier. |
| `DEFAULT_CODE_MODEL` | string | `qwen2.5-coder:7b`| No | Default code generation model identifier. |
| `DEFAULT_EMBEDDING_MODEL` | string | `nomic-embed-text` | No | Embedding model for semantic search. |
| `MODEL_TEMPERATURE` | float | `0.2` | No | Inference sampling temperature. |
| `MODEL_MAX_TOKENS` | integer | `4096` | No | Max completion token cutoff. |

---

## 11. Tool Execution Sandbox (`SANDBOX_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `SANDBOX_TYPE` | string | `docker` | Yes (use `gvisor`) | Container runtime driver (`docker`, `gvisor`, `local`). |
| `SANDBOX_DOCKER_IMAGE` | string | `python:3.11-slim` | No | Base container image for tool execution. |
| `SANDBOX_NETWORK_ISOLATION` | boolean | `true` | Yes | Enforces network detachment for untrusted tools. |
| `SANDBOX_TIMEOUT_SECONDS` | integer | `300` | No | Max execution seconds before killing container. |
| `SANDBOX_MAX_MEMORY_MB` | integer | `1024` | No | Memory limit per sandbox container. |
| `SANDBOX_MAX_CPUS` | float | `1.0` | No | CFS CPU quota per sandbox container. |

---

## 12. Observability & Telemetry (`OTEL_*`)

| Variable | Type | Default | Required in Prod | Description |
|---|---|---|---|---|
| `LOG_LEVEL` | string | `INFO` | No | Minimum logging severity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `LOG_FORMAT` | string | `json` | No | Log formatting: `json` (for Loki) or `text` (local). |
| `OTEL_ENABLED` | boolean | `false` | Yes (set `true`) | Enables OpenTelemetry distributed tracing. |
| `OTEL_SERVICE_NAME` | string | `agent-space-backend` | No | Service identifier emitted on spans. |
| `OTEL_EXPORTER_OTLP_ENDPOINT`| string | `http://localhost:4317` | Yes | OpenTelemetry Collector gRPC/HTTP endpoint. |
| `PROMETHEUS_METRICS_ENABLED` | boolean | `true` | No | Exposes `/metrics` endpoint for Prometheus scraping. |
