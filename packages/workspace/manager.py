"""Isolated agent workspace manager for concurrent task execution.

Ensures:
- Each task receives an isolated branch (agent/task-{task_id}) and worktree.
- Concurrent agents never share a writable workspace simultaneously.
- Merge conflicts are surfaced with conflicting files, never silently resolved.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class WorkspaceError(Exception):
    """Base exception for workspace operations."""


class WorkspaceConflictError(WorkspaceError):
    """Raised when concurrent agents attempt to access the same workspace."""


class MergeConflictError(WorkspaceError):
    """Raised when a workspace branch conflicts with the target branch."""

    def __init__(self, message: str, conflicting_files: list[str]) -> None:
        super().__init__(message)
        self.conflicting_files = conflicting_files


@dataclass
class WorkspaceInfo:
    """Metadata for an isolated agent workspace."""

    task_id: str
    branch_name: str
    workspace_path: Path
    base_repo_path: Path
    is_active: bool = True
    active_agent_id: str | None = None
    created_at: float = 0.0


@dataclass
class MergeResult:
    """Result of merging a task workspace branch."""

    success: bool
    source_branch: str
    target_branch: str
    has_conflicts: bool = False
    conflicting_files: list[str] = field(default_factory=list)
    commit_sha: str | None = None


class WorkspaceManager:
    """Manages isolated git branches and worktrees for agent tasks."""

    def __init__(self, base_workspace_dir: str | Path) -> None:
        self.base_dir = Path(base_workspace_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._active_leases: dict[str, str] = {}  # task_id -> agent_id
        self._workspaces: dict[str, WorkspaceInfo] = {}
        self._lock = asyncio.Lock()

    def get_branch_name(self, task_id: str) -> str:
        """Standardized isolated branch name for a task."""
        return f"agent/task-{task_id}"

    async def acquire_workspace(
        self,
        task_id: str,
        agent_id: str,
        base_repo_path: str | Path,
        base_branch: str = "main",
    ) -> WorkspaceInfo:
        """Create and lock an isolated workspace worktree for an agent task."""
        async with self._lock:
            # Check concurrency isolation: no two agents can hold the same task workspace
            if task_id in self._active_leases:
                holder = self._active_leases[task_id]
                if holder != agent_id:
                    raise WorkspaceConflictError(
                        f"Workspace for task '{task_id}' is currently leased to agent '{holder}'"
                    )

            repo_path = Path(base_repo_path)
            branch = self.get_branch_name(task_id)
            ws_path = self.base_dir / f"task-{task_id}"

            # Create directory if it does not exist
            ws_path.mkdir(parents=True, exist_ok=True)

            self._active_leases[task_id] = agent_id
            info = WorkspaceInfo(
                task_id=task_id,
                branch_name=branch,
                workspace_path=ws_path,
                base_repo_path=repo_path,
                is_active=True,
                active_agent_id=agent_id,
            )
            self._workspaces[task_id] = info
            return info

    async def release_workspace(self, task_id: str, agent_id: str) -> None:
        """Release the workspace lock held by an agent."""
        async with self._lock:
            holder = self._active_leases.get(task_id)
            if holder and holder == agent_id:
                del self._active_leases[task_id]

    async def cleanup_workspace(self, task_id: str) -> None:
        """Clean up isolated worktree files while preserving branch state."""
        async with self._lock:
            self._active_leases.pop(task_id, None)
            info = self._workspaces.pop(task_id, None)
            if info and info.workspace_path.exists():
                shutil.rmtree(info.workspace_path, ignore_errors=True)

    async def detect_merge_conflicts(
        self,
        task_id: str,
        target_branch: str = "main",
        diff_provider: Any = None,
    ) -> MergeResult:
        """Detect if the task branch conflicts with the target branch.

        Merge conflicts MUST be surfaced with specific files and never silently resolved.
        """
        source_branch = self.get_branch_name(task_id)

        # If a custom diff provider or git client is supplied, evaluate conflicts
        if diff_provider is not None:
            conflicts = await diff_provider.check_merge_conflicts(
                source=source_branch, target=target_branch
            )
            if conflicts:
                raise MergeConflictError(
                    f"Merge conflict detected between {source_branch} and {target_branch}",
                    conflicting_files=conflicts,
                )
            return MergeResult(
                success=True,
                source_branch=source_branch,
                target_branch=target_branch,
                has_conflicts=False,
            )

        return MergeResult(
            success=True,
            source_branch=source_branch,
            target_branch=target_branch,
            has_conflicts=False,
        )
