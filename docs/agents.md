# Agent Space Autonomous AI Agent Architecture

Agent Space treats AI agents not as conversational bots, but as **first-class engineering peers** participating in task lifecycles, Git branches, code reviews, and project planning.

---

## 1. Unified Agent Protocol (`agents/protocol.py`)

Every agent implements the standardized `BaseAgent` abstract base class:

```python
class BaseAgent(ABC):
    def __init__(self, name: str, role: str, capabilities: list[str] | None = None, model: str = "llama3.1:8b"):
        ...

    @abstractmethod
    async def execute(self, context: TaskContext) -> AgentResult:
        """Execute task within the provided context and return structured AgentResult."""
```

### `TaskContext`
Input payload delivered to the agent:
- `task_id`: UUID string of target task.
- `project_id`: UUID string of owning project.
- `title` & `description`: Requirements and objective.
- `files`: Scope of target files in the repository.
- `parameters`: Execution parameters and flags (e.g. `require_human_input`).
- `history`: Previous agent steps or handoff state.

### `AgentResult`
Structured outcome produced by the agent:
- `status`: `SUCCESS`, `FAILED`, `BLOCKED`, `NEEDS_HUMAN_INPUT`, or `HANDOFF`.
- `summary`: Human-readable one-line execution summary (safe for live UI feeds).
- `artifacts`: List of generated files (diff patches, specs, reports).
- `changed_files`: List of modified repository paths.
- `tests`: Test execution outcome (`passed`, `failed`, `duration`).
- `handoff`: Target agent role and handoff payload if transitioning to another phase.
- `human_request`: Structured prompt if pausing for human clarification or approval.

---

## 2. Specialized Agent Roles

| Agent Class | Role Enum | Key Responsibilities |
|---|---|---|
| `ProjectManagerAgent` | `COORDINATOR` | Decomposes high-level objectives into work breakdown structures, task DAGs, and milestones. |
| `ResearchAgent` | `RESEARCHER` | Investigates technical approaches, sanitizes external web/repo data, synthesizes research findings. |
| `ArchitectAgent` | `ARCHITECT` | Defines system components, REST API contracts, database schemas, and non-functional requirements. |
| `CodingAgent` | `DEVELOPER` | Inspects workspace, writes code changes, runs tests, generates unified diff patches, and commits. |
| `TestingAgent` | `TESTER` | Executes test suites, analyzes failures, evaluates edge cases, and produces test reports. |
| `ReviewerAgent` | `REVIEWER` | Multi-pillar review (Requirements, Diff, Tests, Security), assigns severity levels, issues approval verdict. |
| `VisionAgent` | `RESEARCHER` | Analyzes UI screenshots, wireframes, and architectural diagrams. |

---

## 3. Cognitive Runtime Engine (LangGraph)

Agent decision-making is implemented as a state graph (`AgentRuntime`):

```text
[Context Ingestion] ──> [Reasoning Node] ──> [Tool Selection]
                                ▲                    │
                                │                    ▼
                        [Observation] <──── [Tool Execution]
                                │
                          (Completed)
                                ▼
                       [Sanitized Finish]
```

### Invariant: Zero Chain-of-Thought Exposure
Internal reasoning tokens (`thought`, `thinking`, `plan_scratchpad`) are isolated within node scratchpads and strictly excluded from the final `AgentResult` and domain activity feeds.

---

## 4. Model Gateway (`agents/model_gateway.py`)

A pluggable LLM abstraction layer providing unified inference across local and hosted models:

- **Providers**: `OllamaProvider` (local development), `VLLMProvider` (high-throughput production GPU clusters), and `MockModelProvider` (deterministic CI testing).
- **Resilience**: Automatic retry with exponential backoff on model failure or rate limit.
- **Observability**: Records token count, prompt latency, and model identifier in OpenTelemetry spans.
