"""Tests for M31 — Workflow Signals & Human Input.

Validates:
- pause and resume signals and is_paused query
- human_input signal handling
- approval signal handling (approved vs rejected)
- takeover signal handling
- handoff signal handling
"""

from app.temporal.workflows.task_workflow import TaskWorkflow


class TestWorkflowSignals:
    def test_pause_and_resume_signals(self) -> None:
        wf = TaskWorkflow()
        assert wf.is_paused() is False
        assert wf.state()["status"] == "INITIALIZED"

        # Signal pause
        wf.pause()
        assert wf.is_paused() is True
        assert wf.state()["status"] == "PAUSED"
        assert wf.state()["paused"] is True

        # Signal resume
        wf.resume()
        assert wf.is_paused() is False
        assert wf.state()["status"] == "RUNNING"
        assert wf.state()["paused"] is False

    def test_human_input_signal(self) -> None:
        wf = TaskWorkflow()
        payload = {"feedback": "Looks great, please proceed with tests"}

        wf.human_input(payload)
        state = wf.state()
        assert state["human_input"] == payload

    def test_approval_signals(self) -> None:
        # Approved case
        wf1 = TaskWorkflow()
        wf1.approval(approved=True, reason="Code review approved by Lead")
        state1 = wf1.state()
        assert state1["approval"]["approved"] is True
        assert state1["approval"]["reason"] == "Code review approved by Lead"

        # Rejected case
        wf2 = TaskWorkflow()
        wf2.approval(approved=False, reason="Missing error handling in repo")
        state2 = wf2.state()
        assert state2["approval"]["approved"] is False
        assert state2["approval"]["reason"] == "Missing error handling in repo"

    def test_takeover_signal(self) -> None:
        wf = TaskWorkflow()
        user_id = "user-human-456"

        wf.takeover(user_id)
        state = wf.state()
        assert state["taken_over_by"] == user_id
        assert state["status"] == "HUMAN_TAKEOVER"

    def test_handoff_signal(self) -> None:
        wf = TaskWorkflow()
        payload = {
            "from_agent_id": "coder-1",
            "to_entity_id": "reviewer-2",
            "reason": "Ready for security review",
        }

        wf.handoff(payload)
        state = wf.state()
        assert state["handoff"] == payload
        assert state["agent_id"] == "reviewer-2"
