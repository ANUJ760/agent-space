# Agent Space Operational Troubleshooting & Incident Runbook

This guide outlines diagnostic procedures, root cause analysis, and resolution steps for operational incidents.

---

## 1. Quick Diagnostics & Health Checks

Verify individual subsystems using the health API:

```bash
# General readiness check (checks DB, Redis, Temporal connectivity)
curl -i http://localhost:8000/health/readiness

# Kubernetes pod status
kubectl get pods -n agentspace -o wide

# Check backend container logs
kubectl logs -n agentspace -l app.kubernetes.io/component=backend --tail=100 -f
```

---

## 2. Common Operational Incidents

### A. Database Connection Pool Exhaustion
- **Symptom**: HTTP 500 responses with `TimeoutError: QueuePool limit of size X overflow Y reached`.
- **Root Cause**: Unclosed sessions or long-running database transactions during heavy traffic.
- **Resolution**:
  1. Check active connections in PostgreSQL:
     ```sql
     SELECT pid, usename, state, query_start, query FROM pg_stat_activity WHERE state != 'idle';
     ```
  2. Increase pool size in environment variables:
     ```bash
     DB_POOL_SIZE=30
     DB_MAX_OVERFLOW=20
     ```
  3. Restart backend pods: `kubectl rollout restart deployment/agentspace-backend -n agentspace`.

### B. Temporal Worker Lag / Missing Heartbeats
- **Symptom**: Tasks remain in `CLAIMED` status; `WorkerHeartbeatMissing` alert fires.
- **Root Cause**: Worker pod crashed or ran out of memory while executing an agent task.
- **Resolution**:
  1. Inspect Temporal Web UI at `http://localhost:8233` and inspect workflow execution history.
  2. Check worker logs: `kubectl logs -n agentspace -l app.kubernetes.io/component=worker --tail=200`.
  3. Scale up worker replicas: `kubectl scale deployment/agentspace-worker -n agentspace --replicas=5`.

### C. OIDC / Keycloak Token Verification Failure
- **Symptom**: HTTP 401 Unauthorized with `{"code": "AUTH_INVALID_TOKEN", "message": "Signature verification failed"}`.
- **Root Cause**: Keycloak realm public key rotated, or backend unable to contact Keycloak JWKS endpoint.
- **Resolution**:
  1. Verify backend can reach Keycloak:
     ```bash
     curl -i http://keycloak:8080/realms/agentspace/.well-known/openid-configuration
     ```
  2. Clear backend JWKS cache by restarting backend pods.
  3. Ensure system clocks are synchronized (NTP) to prevent clock-skew errors.

### D. Sandboxed Container OOM Killed
- **Symptom**: Agent task fails with `ContainerKilledError: Sandbox exceeded memory limit (2048 MB)`.
- **Root Cause**: Memory-intensive compilation, large dataset processing, or runaway subprocess in agent code.
- **Resolution**:
  1. Inspect task log in CAS artifacts to determine memory consumer.
  2. For authorized resource-heavy workloads, increase limits in `app.config.Settings`:
     ```bash
     SANDBOX_MAX_MEMORY_MB=4096
     ```

### E. Stale Git Worktree Locks
- **Symptom**: Agent reports `fatal: Unable to create '.git/index.lock': File exists`.
- **Root Cause**: Worker pod was killed abruptly during a Git commit operation.
- **Resolution**:
  1. Check out the worktree directory on Gitea or the persistent volume.
  2. Clean up dangling locks:
     ```bash
     find /workspace/worktrees -name "*.lock" -delete
     ```

---

## 3. Disaster Recovery & Emergency Restore

In the event of total database corruption or cluster loss, execute the disaster recovery procedure:

```bash
# 1. Ensure target database and storage are clean
python -m packages.backup.cli restore --full --archive /backups/agentspace_backup_latest.tar.gz

# 2. Verify integrity
python -m packages.backup.cli verify --db-check --artifact-check
```

Detailed RPO/RTO specifications and validation steps are located in [`docs/backup_restore.md`](backup_restore.md).
