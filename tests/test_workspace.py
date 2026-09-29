"""Unit tests for isolated agent workspaces and concurrency control."""

from pathlib import Path

import pytest

from packages.workspace.manager import (
    MergeConflictError,
    WorkspaceConflictError,
    WorkspaceManager,
)


@pytest.fixture
def workspace_manager(tmp_path: Path):
    return WorkspaceManager(base_workspace_dir=tmp_path / "workspaces")


@pytest.mark.asyncio
async def test_workspace_acquisition(workspace_manager, tmp_path: Path):
    repo_path = tmp_path / "main-repo"
    repo_path.mkdir()

    ws = await workspace_manager.acquire_workspace(
        task_id="task-42",
        agent_id="agent-alice",
        base_repo_path=repo_path,
    )

    assert ws.task_id == "task-42"
    assert ws.branch_name == "agent/task-task-42"
    assert ws.workspace_path.exists()
    assert ws.active_agent_id == "agent-alice"


@pytest.mark.asyncio
async def test_concurrent_agent_workspace_conflict(workspace_manager, tmp_path: Path):
    repo_path = tmp_path / "main-repo"
    repo_path.mkdir()

    # Agent Alice acquires workspace
    await workspace_manager.acquire_workspace(
        task_id="task-100",
        agent_id="agent-alice",
        base_repo_path=repo_path,
    )

    # Agent Bob attempts to acquire same task workspace -> must raise Conflict
    with pytest.raises(WorkspaceConflictError) as exc_info:
        await workspace_manager.acquire_workspace(
            task_id="task-100",
            agent_id="agent-bob",
            base_repo_path=repo_path,
        )
    assert "agent-alice" in str(exc_info.value)

    # Re-acquisition by Alice succeeds
    ws = await workspace_manager.acquire_workspace(
        task_id="task-100",
        agent_id="agent-alice",
        base_repo_path=repo_path,
    )
    assert ws.active_agent_id == "agent-alice"

    # Alice releases workspace
    await workspace_manager.release_workspace("task-100", "agent-alice")

    # Bob can now acquire it
    ws_bob = await workspace_manager.acquire_workspace(
        task_id="task-100",
        agent_id="agent-bob",
        base_repo_path=repo_path,
    )
    assert ws_bob.active_agent_id == "agent-bob"


@pytest.mark.asyncio
async def test_merge_conflicts_surfaced(workspace_manager):
    class MockConflictGit:
        async def check_merge_conflicts(self, source: str, target: str):
            return ["src/auth.py", "pyproject.toml"]

    with pytest.raises(MergeConflictError) as exc_info:
        await workspace_manager.detect_merge_conflicts(
            task_id="task-200",
            target_branch="main",
            diff_provider=MockConflictGit(),
        )

    assert exc_info.value.conflicting_files == ["src/auth.py", "pyproject.toml"]


@pytest.mark.asyncio
async def test_workspace_cleanup(workspace_manager, tmp_path: Path):
    repo_path = tmp_path / "main-repo"
    repo_path.mkdir()

    ws = await workspace_manager.acquire_workspace(
        task_id="task-300",
        agent_id="agent-carol",
        base_repo_path=repo_path,
    )
    ws_dir = ws.workspace_path
    assert ws_dir.exists()

    await workspace_manager.cleanup_workspace("task-300")
    assert not ws_dir.exists()
