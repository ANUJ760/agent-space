# Disaster Recovery, Backup, and Restore Specifications (M87)

This document formalizes the enterprise disaster recovery (DR) architecture, recovery objectives, and step-by-step procedures for AgentSpace across all 5 stateful domains.

---

## 1. Recovery Objectives (RPO & RTO)

| Metric | Target | Operational Assumptions & Mechanisms |
| :--- | :--- | :--- |
| **Recovery Point Objective (RPO)** | **< 15 minutes** | Continuous PostgreSQL Write-Ahead Log (WAL) archiving via WAL-G / AWS S3 replication; CAS artifacts are immutable content-addressable storage written synchronously to durable S3/Azure Blob; Git push hooks trigger atomic repository mirroring. |
| **Recovery Time Objective (RTO)** | **< 30 minutes** | Fully automated single-command rehydration via `BackupRestoreService`; parallel table ingestion and volume extraction; pre-provisioned cold/warm standby infrastructure in secondary availability zone. |

---

## 2. Backup Domains & Scope

The AgentSpace disaster recovery engine captures complete state across 5 core pillars:

```text
┌─────────────────────────────────────────────────────────────┐
│                  AgentSpace Full Backup                     │
└──────┬─────────────┬─────────────┬─────────────┬────────────┘
       │             │             │             │            │
       ▼             ▼             ▼             ▼            ▼
┌──────────────┐┌──────────────┐┌──────────────┐┌───────────┐┌───────────────┐
│  PostgreSQL  ││   Artifact   ││     CAS      ││   Gitea   ││   Keycloak    │
│  DB Records  ││   Metadata   ││   Artifacts  ││ Git Repos ││ Configuration │
│ (Users, Orgs,││ (Loc, hashes,││ (S3/Blob CAS ││ (Bare Git ││(Realm, roles, │
│ Tasks, Projs)││  MIME, sizes)││   storage)   ││ branches) ││ clients, IDP) │
└──────────────┘└──────────────┘└──────────────┘└───────────┘└───────────────┘
```

1. **PostgreSQL Database**:
   - Master data: Organizations, Users, Projects, Project Members, Tasks, Dependencies, Audit Logs, Task Workflow States.
   - Mechanism: Logical JSON dump / `pg_dump` with transaction snapshot isolation.

2. **Artifact Metadata**:
   - Schema mapping storage keys to task IDs, project IDs, MIME types, loc counts, and SHA-256 integrity hashes.

3. **Content Addressable Storage (CAS) Artifacts**:
   - Binary code patches, diffs, test logs, summaries, models, and uploaded files stored in S3/Azure Blob.
   - Integrity: Each file verified against stored SHA-256 digest on both backup and restore.

4. **Gitea Git Repositories**:
   - Bare Git repositories containing commit trees, feature branches, tags, and PR review references.
   - Archive: Compressed `tar.gz` bundle preserving Git object directories and hooks.

5. **Keycloak Configuration**:
   - Identity management state: Realm definitions, OIDC client secrets, RBAC role mappings, and token signing key specifications.

---

## 3. Disaster Recovery Execution Runbook

### Full Backup Execution
```bash
python -m packages.backup.cli create --output /backups/agentspace-full-$(date +%s).tar.gz
```

### Full Restore Execution
```bash
python -m packages.backup.cli restore --archive /backups/agentspace-full-latest.tar.gz
```

### Verification Checks
1. Database record count assertions: `SELECT count(*) FROM tasks;`
2. Artifact CAS integrity: Re-hash all binary files against `sha256_hash` in `artifacts` table.
3. Git consistency: `git fsck --full` on restored repositories.
4. Identity validation: Execute test OIDC token verification against restored Keycloak realm.
