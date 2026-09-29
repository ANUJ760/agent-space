"""Task DAG dependency-aware execution engine (M60).

Features:
- Cycle prevention via Kahn's algorithm / DFS.
- Identifies parallel execution stages (e.g. A and B concurrently, then C, then D).
- Determines executable ready tasks based on completed task prerequisites.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


class CycleDependencyError(Exception):
    """Raised when circular dependencies exist between tasks."""

    def __init__(self, message: str, cycle_nodes: list[str] | None = None) -> None:
        super().__init__(message)
        self.cycle_nodes = cycle_nodes or []


@dataclass
class DAGExecutionStage:
    """A batch of tasks that can safely execute concurrently in parallel."""

    stage_index: int
    task_ids: list[str] = field(default_factory=list)


class TaskDAGExecutor:
    """Manages DAG dependency resolution and parallel execution staging."""

    def __init__(self) -> None:
        # dependency_graph[task_id] = set of dependency_task_ids (prerequisites)
        self._prerequisites: dict[str, set[str]] = defaultdict(set)
        # dependents[task_id] = set of downstream tasks waiting for task_id
        self._dependents: dict[str, set[str]] = defaultdict(set)
        self._all_tasks: set[str] = set()

    def add_task(self, task_id: str) -> None:
        self._all_tasks.add(task_id)

    def add_dependency(self, task_id: str, depends_on_task_id: str) -> None:
        """task_id depends on depends_on_task_id (depends_on must finish first)."""
        self._all_tasks.add(task_id)
        self._all_tasks.add(depends_on_task_id)
        self._prerequisites[task_id].add(depends_on_task_id)
        self._dependents[depends_on_task_id].add(task_id)

    def validate_acyclic(self) -> None:
        """Validate that the graph has no cycles. Raises CycleDependencyError if a cycle is found."""
        in_degree = {t: len(self._prerequisites[t]) for t in self._all_tasks}
        queue = deque([t for t, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for downstream in self._dependents[node]:
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)

        if visited_count != len(self._all_tasks):
            unvisited = [t for t, deg in in_degree.items() if deg > 0]
            raise CycleDependencyError(
                f"Cyclic dependency detected among tasks: {', '.join(unvisited)}",
                cycle_nodes=unvisited,
            )

    def compute_parallel_stages(self) -> list[DAGExecutionStage]:
        """Group tasks into discrete topological stages for parallel execution."""
        self.validate_acyclic()

        # Compute level for each task (max distance from root)
        levels: dict[str, int] = {}

        def get_level(t: str) -> int:
            if t in levels:
                return levels[t]
            prereqs = self._prerequisites[t]
            if not prereqs:
                levels[t] = 0
                return 0
            lvl = 1 + max(get_level(p) for p in prereqs)
            levels[t] = lvl
            return lvl

        for t in self._all_tasks:
            get_level(t)

        stages_map: dict[int, list[str]] = defaultdict(list)
        for t, lvl in levels.items():
            stages_map[lvl].append(t)

        stages: list[DAGExecutionStage] = []
        for lvl in sorted(stages_map.keys()):
            stages.append(DAGExecutionStage(stage_index=lvl, task_ids=sorted(stages_map[lvl])))

        return stages

    def get_ready_tasks(
        self, completed_task_ids: set[str], in_progress_task_ids: set[str] | None = None
    ) -> list[str]:
        """Return all tasks whose prerequisites are completely satisfied and not yet in-flight."""
        self.validate_acyclic()
        in_flight = in_progress_task_ids or set()
        ready: list[str] = []

        for task_id in sorted(self._all_tasks):
            if task_id in completed_task_ids or task_id in in_flight:
                continue
            prereqs = self._prerequisites[task_id]
            if prereqs.issubset(completed_task_ids):
                ready.append(task_id)

        return ready
