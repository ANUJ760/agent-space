# Agent Space Production Observability & Monitoring

Agent Space integrates a full cloud-native observability stack based on **OpenTelemetry**, **Prometheus**, **Alertmanager**, **Loki**, and **Grafana**.

---

## 1. Observability Architecture

```text
┌─────────────────┐       ┌─────────────────┐
│     Backend     │       │     Workers     │
│ (FastAPI + OTel)│       │ (Temporal+OTel) │
└────────┬────────┘       └────────┬────────┘
         │ Traces (OTLP)           │ Logs (JSON)
         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐
│  OTel Collector │       │      Loki       │
│  (4317 / 4318)  │       │  (Log Engine)   │
└────────┬────────┘       └────────┬────────┘
         │                         │
         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐
│   Prometheus    │──────>│     Grafana     │
│ (Metrics Engine)│       │   (Dashboards)  │
└────────┬────────┘       └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Alertmanager   │
│  (8 Prod Rules) │
└─────────────────┘
```

---

## 2. Distributed Tracing (OpenTelemetry)

- **Collector**: `infrastructure/opentelemetry/otel-collector-config.yml` accepts OTLP traces over gRPC (`4317`) and HTTP (`4318`).
- **Context Propagation**: Standard W3C TraceContext headers (`traceparent`, `tracestate`) propagated across HTTP requests, Temporal workflows, and NATS event messages.
- **Span Annotations**: Every trace captures `organization_id`, `project_id`, `task_id`, `agent_role`, and database query duration.

---

## 3. Metrics & Alerting (Prometheus & Alertmanager)

Prometheus scrapes application and infrastructure endpoints every 15 seconds.

### The 8 Production Alert Rules (`infrastructure/prometheus/alerts/production_alerts.yml`):

1. **`HighHttpErrorRate`**: Triggers when 5xx HTTP error rate exceeds 5% over 5 minutes.
2. **`HighHttpLatency`**: Triggers when 95th percentile HTTP latency exceeds 1.5 seconds over 5 minutes.
3. **`TemporalWorkflowFailures`**: Triggers when Temporal workflow execution failure rate exceeds 2% over 5 minutes.
4. **`DatabaseConnectionPoolExhaustion`**: Triggers when active database connections exceed 85% of total pool capacity.
5. **`RedisMemoryExhaustion`**: Triggers when Redis memory utilization exceeds 85% of maxmemory.
6. **`WorkerHeartbeatMissing`**: Triggers when an agent worker fails to send liveness heartbeats for >60 seconds.
7. **`AgentTaskQueueLag`**: Triggers when unassigned tasks in the scheduling queue exceed 25 for >10 minutes.
8. **`StorageDiskSpaceLow`**: Triggers when persistent volume free space drops below 15%.

---

## 4. Structured Logging (Loki)

- **Log Format**: Machine-readable JSON logs produced by Python `structlog` and Next.js logger.
- **Correlation**: Every log line carries `request_id`, `trace_id`, and `tenant_id`.
- **Sensitive Data Masking**: Log pipelines automatically mask JWT tokens, Authorization headers, passwords, and private keys.
- **Chain-of-Thought Protection**: Internal reasoning tokens are purged before log emission.

---

## 5. Dashboards (Grafana)

Grafana is pre-configured via `infrastructure/grafana/datasources/datasources.yml`:
- **Prometheus**: Primary metrics provider.
- **Loki**: Log analysis provider with log-to-trace navigation.
- **Alertmanager**: Real-time incident alert status.
