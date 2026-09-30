# Agent Space Tool Gateway & Code Sandbox Architecture

Autonomous AI agents generate and execute code, invoke shell utilities, and interact with filesystems. To safeguard host nodes and prevent lateral movement, Agent Space routes all tool executions through the **Tool Gateway** into an **isolated sandbox environment**.

---

## 1. Sandbox Isolation Model

```text
┌────────────────────────────────────────────────────────┐
│ Host Operating System / Worker Node                    │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ gVisor / runsc Container Barrier                 │  │
│  │                                                  │  │
│  │  - User: uid 10001 (non-root)                    │  │
│  │  - Root Filesystem: READ-ONLY                    │  │
│  │  - Capabilities: DROP ALL                        │  │
│  │  - Network: NONE (or egress proxy)               │  │
│  │  - CPU Quota: 2.0 cores                          │  │
│  │  - Memory Quota: 2048 MB                         │  │
│  │  - PID Limit: 128                                │  │
│  │                                                  │  │
│  │   ┌──────────────────┐    ┌──────────────────┐   │  │
│  │   │ /workspace       │    │ /tmp             │   │  │
│  │   │ (Ephemeral Vol)  │    │ (tmpfs in-memory)│   │  │
│  │   └──────────────────┘    └──────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 2. Security Boundaries & Invariants

1. **User-Space Kernel Emulation**: In production Kubernetes clusters, sandboxes utilize `runsc` (gVisor). System calls are intercepted in user-space, preventing direct communication with the host Linux kernel.
2. **Non-Root Principle**: All processes run under `uid=10001:gid=10001` with `allowPrivilegeEscalation: false`.
3. **Read-Only Root Filesystem**: The container root (`/`) is strictly read-only. Attempts to write to `/usr`, `/etc`, or system libraries trigger `EROFS (Read-only file system)`.
4. **Linux Capabilities**: All Linux capabilities are dropped (`capDrop: ["ALL"]`).
5. **Network Policy**: Container network namespace is detached (`NetworkMode: "none"`). If dependency downloads are authorized, traffic passes through an egress proxy enforcing DNS and domain whitelists.

---

## 3. Resource Governance & Quotas

To prevent fork-bombs, memory exhaustion, or CPU starvation:

| Resource | Constraint | Enforcement Mechanism |
|---|---|---|
| Memory | 2048 MB Limit | cgroup memory limit (`oom_kill_disable: false`) |
| CPU | 2.0 Cores Max | cgroup `cpu.cfs_quota_us` |
| Processes | 128 PIDs Max | cgroup `pids.max` (blocks fork-bombs) |
| Wall-Clock Time | 300 Seconds | Python async timeout + SIGKILL |
| Disk Output | 500 MB Max | Filesystem quota on `/workspace` volume |

---

## 4. Tool Gateway (`packages/tool_gateway`)

Before any agent tool is executed, it is evaluated by the **Tool Gateway**:

1. **Permission Check**: Verifies that the agent role possesses capability tags for the requested tool (e.g. `CodingAgent` requires `AgentCapability.GIT` to invoke `git` commands).
2. **Path Sanitization**: Guarantees file operations remain strictly contained within `/workspace`. Paths with directory traversal (`../`) or absolute host paths are rejected immediately.
3. **Command Blacklist**: Disallows dangerous shell primitives (`sudo`, `su`, `chown`, `chmod +s`, `mkfs`, raw block device writes).
