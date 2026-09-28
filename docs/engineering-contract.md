# Agent Space — Engineering Contract & Review Protocol

## 1. Core Rule: One Module at a Time

Agent Space is built modularly with human review gates between every module:

```text
START MODULE
    ↓
Inspect existing implementation
    ↓
Implement ONLY this module
    ↓
Write/update tests for this module
    ↓
Run required verification
    ↓
Fix failures
    ↓
Document module
    ↓
Show human review report
    ↓
STOPPING NOW FOR REVIEW.
```

**Human approval is the gate between modules.** Never proceed automatically to the next module.

---

## 2. Completion Protocol Template

Every module completion must end with the standardized report:

```text
==================================================
MODULE COMPLETE
==================================================

Module: MXX — <name>

Implemented:
- ...

Files created:
- ...

Files modified:
- ...

Interfaces:
- ...

Database:
- ...

Tests:
- ...

Commands run:
- ...

Verification:
- PASS / FAIL

Security:
- ...

Concurrency:
- ...

Known limitations:
- ...

Next planned module:
- MXX

Human review checklist:
[ ] ...
[ ] ...

STOPPING NOW FOR REVIEW.
==================================================
```

---

## 3. Engineering Quality Gates

Before any module is submitted for human review, it must meet these standards:

1. **Correctness**: The module must fulfill its stated scope without stubbing essential features.
2. **Architecture**: Boundaries between FastAPI, PostgreSQL, Redis, Temporal, NATS, and Sandboxes must not be violated.
3. **Security**: No secrets hardcoded. Input validation via Pydantic schemas. Object-level authorization respected.
4. **Concurrency**: Safe state updates. Explicit handling of race conditions and stale versions.
5. **Testing**: Automated unit/integration tests covering both happy and error paths.
6. **Code Quality**: Formatted with Ruff, passes static typing with Mypy, clean git status.
