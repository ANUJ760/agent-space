# Sandbox Security Audit & Threat Model (M66)

## 1. Executive Summary

This document reports the adversarial security testing and verification performed on the Agent Space Docker execution sandbox runtime. Sandboxes execute untrusted LLM-generated code and third-party tools; therefore, multi-layered isolation, least privilege, and container breakout defenses are mandatory invariants.

---

## 2. Adversarial Test Matrix & Audit Results

| Threat Category | Attack Vector | Security Control | Audit Status |
|---|---|---|---|
| **Docker Socket Abuse** | Mounting `/var/run/docker.sock` or command execution targeting the daemon | Mount denylist + command pattern filtering | **PASS** (Blocked with `DockerSecurityViolationError`) |
| **Host Filesystem Mounts** | Mounting `/`, `/etc`, `/proc`, `/sys`, `/root`, `/var` or traversal paths | Absolute & normalized path validation | **PASS** (Strictly forbidden) |
| **Privilege Escalation** | Requesting `privileged=True`, root UID `0`, or `user="root"` | Invariant assertions + `cap_drop: ALL` + `no-new-privileges` | **PASS** (Blocked at policy creation) |
| **Network Escape & SSRF** | Egress to loopback (`127.0.0.1`), RFC1918 subnets, cloud metadata (`169.254.169.254`), or internal services | `NetworkPolicy.DENY` default + DNS/IP egress filter | **PASS** (Blocked with `NetworkEgressBlockedError`) |
| **Resource Exhaustion** | Memory bombs, excessive disk writes, unbounded stdout/stderr | Hard container memory limits + `ResourceGovernor` stream truncation | **PASS** (Truncated & killed on threshold) |
| **Fork Bomb** | Recursive subprocess spawning | Kernel PID cgroups (`pids_limit: 50-100`) | **PASS** (Blocked by PID quota) |
| **Secret Discovery** | Reading host environment variables or dumping credentials | Isolated container env injection + dynamic `SecretMasker` | **PASS** (Credentials scrubbed) |
| **Container Breakouts** | Kernel escape primitives (`nsenter`, `chroot`, `/dev/mem`, `/dev/kmem`) | Exec-level pattern auditing + dropped capabilities + read-only rootfs | **PASS** (Killed with exit code 126) |

---

## 3. Defense-in-Depth Architecture

```text
Untrusted Execution Request
         │
         ▼
[ Policy Validation ]  ──► Rejects root UID, privileged mode, bad PID limits
         │
         ▼
[ Mount Sanity Check ] ──► Normalizes paths, blocks Docker socket & sensitive dirs
         │
         ▼
[ Container Hardening ]──► read_only rootfs, tmpfs with noexec, cap_drop ALL
         │
         ▼
[ Network Gateway ]    ──► DENY by default, blocks RFC1918/Loopback/Metadata/DNS rebinding
         │
         ▼
[ Resource Governor ]  ──► PID limit (fork bomb defense), Memory limit, Output truncation
         │
         ▼
[ Secret Masker ]      ──► Scrub secrets before stdout/stderr reaches logs or agents
```

---

## 4. Residual Risks & Production Mitigations

1. **Linux Kernel Zero-Days (Container Escapes):**
   - *Residual Risk:* Standard Linux namespaces and cgroups share the host kernel. A kernel zero-day vulnerability (e.g., Dirty COW, Dirty Cred) could theoretically allow privilege escalation.
   - *Mitigation:* In production, Agent Space should deploy microVM hypervisor isolation (such as **gVisor** `runsc` or **Firecracker / Kata Containers**) for untrusted multi-tenant workloads.
2. **Side-Channel & CPU Cache Timing Attacks (Spectre/Meltdown):**
   - *Residual Risk:* Co-located multi-tenant agent execution on the same physical CPU core could permit microarchitectural timing measurements.
   - *Mitigation:* Ensure strict core pinning and hyper-threading sibling core isolation on shared host clusters.
3. **DNS Rebinding in Allowed External Network Mode:**
   - *Residual Risk:* If a tenant enables allowlisted external network egress, a hostile DNS server could return a public IP on first resolve and an RFC1918 IP on actual TCP connection.
   - *Mitigation:* The egress proxy validates both resolved DNS IPs at query time and pins resolved IPs before initiating TCP handshakes.
