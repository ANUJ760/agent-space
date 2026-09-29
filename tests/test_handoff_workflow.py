"""Integration tests for M54 (Human to Agent Handoff).

Validates:
- Human finishes manual work on isolated task branch
- Releases task ownership and assigns agent with resumption instructions
- Agent runtime resumes with current repository state
"""

import uuid

import pytest

from agents.protocol import AgentExecutionStatus, AgentResult, BaseAgent, TaskContext
from packages.workspace.manager import WorkspaceManager


class ResumingAgent(BaseAgent):
    """Test agent verifying it receives handoff instructions and repo state."""

    async def execute(self, context: TaskContext) -> AgentResult:
        instructions = context.metadata.get("handoff_instructions")
        return AgentResult(
            status=AgentExecutionStatus.SUCCESS,
            summary=f"Resumed and processed: {instructions}",
            changed_files=["src/main.py"],
        )


@pytest.mark.asyncio
async def test_human_to_agent_handoff_sequence(tmp_path):
    ws_mgr = WorkspaceManager(base_workspace_dir=tmp_path / "workspaces")
    task_id = "task-handoff-99"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # 1. Human acquires workspace
    human_ws = await ws_mgr.acquire_workspace(
        task_id=task_id,
        agent_id="human-alice",
        base_repo_path=repo_path,
    )
    # Human writes file
    target_file = human_ws.workspace_path / "src" / "main.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("def solve(): pass\n")

    # 2. Human releases workspace ownership
    await ws_mgr.release_workspace(task_id, "human-alice")

    # 3. Agent acquires workspace and resumes
    agent_ws = await ws_mgr.acquire_workspace(
        task_id=task_id,
        agent_id="agent-bob",
        base_repo_path=repo_path,
    )
    assert agent_ws.active_agent_id == "agent-bob"

    # Agent inspects workspace and sees human's edits
    resumed_file = agent_ws.workspace_path / "src" / "main.py"
    assert resumed_file.exists()
    assert "def solve():" in resumed_file.read_text()

    # Agent executes with handoff instructions
    agent = ResumingAgent(name="resuming-bot", role="developer")
    ctx = TaskContext(
        task_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        title="Continue work",
        metadata={"handoff_instructions": "Please implement solve() body."},
    )
    result = await agent.execute(ctx)
    assert result.status == AgentExecutionStatus.SUCCESS
    assert "Please implement solve() body." in result.summary
