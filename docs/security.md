# Agent Space Security Architecture & Compliance Specification

Agent Space is engineered with defense-in-depth across the entire application stack, from multi-tenant REST boundaries to autonomous agent code sandboxes.

---

## 1. Authentication (OIDC & Keycloak)

- **Identity Standard**: OpenID Connect (OIDC) and OAuth 2.0 with PKCE for interactive login.
- **Token Signing**: Asymmetric RS256 JSON Web Tokens (JWT) signed by Keycloak.
- **Verification Engine**: Backend validates token signature against Keycloak JWKS endpoint with cached public keys, issuer checks, audience validation, and 60-second clock skew tolerance.
- **Session Lifecycle**: Stateless access tokens with short TTL (15 minutes); rotating refresh tokens with automatic revocation.

---

## 2. Role-Based Access Control (RBAC)

Hierarchical roles govern access across organizational and project scopes:

| Role | Scope | Permissions |
|---|---|---|
| `SYSTEM_ADMIN` | Global | Manage all organizations, system telemetry, platform-wide configurations. |
| `ORG_ADMIN` | Organization | Manage organization users, billing, projects, agent registrations, audit logs. |
| `PROJECT_MAINTAINER`| Project | Create/archive projects, add members, assign tasks, configure repositories. |
| `DEVELOPER` / `AGENT` | Project | Claim tasks, submit code diffs, run tests, request reviews, emit events. |
| `OBSERVER` | Project | Read-only access to projects, tasks, live activity feeds, and metrics. |

Every API endpoint enforces declarative permission checks via `authorize_project_access()` and `authorize_object_access()`.

---

## 3. Multi-Tenant Isolation & IDOR Protection

1. **Strict Organization Scoping**: All relational queries include `WHERE organization_id = :actor_org_id`.
2. **Anti-IDOR Policy**: Requesting an entity (Project, Task, Artifact) belonging to another organization responds with `404 Not Found` rather than `403 Forbidden` to prevent resource enumeration attacks.
3. **Database Cascading**: Deleting an organization or project cascades all child records via foreign key constraints, leaving zero orphaned tenant data.

---

## 4. Agent Sandboxing (gVisor / Docker)

Untrusted agent code execution, test runs, and shell tools execute in isolated sandboxes:

- **Runtime**: `runsc` (gVisor) intercepting system calls in user-space, preventing kernel exploits.
- **Non-Root Execution**: Runs as non-root user `uid=10001:gid=10001` with `no-new-privileges:true`.
- **Read-Only Root Filesystem**: Root filesystem is mounted read-only (`readOnlyRootFilesystem: true`). Ephemeral writes restricted to temporary in-memory tmpfs mounts.
- **Resource Constraints**: Strict limits enforced via cgroups:
  - Max Memory: 2GB per sandbox
  - Max CPU: 2.0 cores
  - Max PIDs: 128
  - Timeout: 300 seconds hard kill
- **Network Isolation**: Disabled by default (`none`). If external package installation is required, outbound traffic is routed through an egress HTTP proxy with domain whitelisting.

---

## 5. Secret Zero-Exposure Guarantee

1. **Zero Secret Leakage in Infrastructure Code**: OpenTofu/Terraform templates strictly forbid exporting plaintext passwords, keys, or tokens in root module outputs. Secrets are managed through AWS Secrets Manager or Azure Key Vault.
2. **Log Sanitization**: Structured logs (`structlog`) pass through an automated masking filter redacting passwords, tokens, Authorization headers, and private keys.
3. **Activity Feed Privacy**: Internal agent reasoning (`thought`, `thinking`, `plan_scratchpad`) is stripped at the gateway before formatting client-facing activity feed items.

---

## 6. SSRF Protection & URL Validation

Any agent tool accepting external URLs (e.g. web search, target service benchmarking, URL shortener redirection) validates destination targets:

- Prohibits loopback interfaces (`127.0.0.0/8`, `::1`, `localhost`).
- Prohibits private networks (RFC 1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- Prohibits cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`).
- Enforces DNS rebinding protection via resolved IP validation before socket connection.

---

## 7. Malicious Upload & CAS Storage Security

Artifact uploads (patches, logs, binaries) are stored in an immutable Content-Addressable Storage (CAS) layout:

- **Storage Key**: SHA-256 hash of file contents (`sha256:{hash}`).
- **Path Traversal Protection**: Filenames are sanitized, stripping directory separators (`/`, `\`, `..`).
- **MIME Validation**: Magic byte inspection verifies true content types.
- **Quota Limits**: 50MB per single artifact; 10GB per project quota.
- **Execution Prevention**: CAS buckets serve files with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.
