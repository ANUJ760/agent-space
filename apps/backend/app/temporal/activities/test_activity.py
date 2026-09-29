"""Test activities for Temporal worker infrastructure."""

from typing import Any

from temporalio import activity


@activity.defn
async def trivial_activity(input_str: str) -> str:
    """A trivial test activity used to verify worker infrastructure."""
    activity.logger.info("executing_trivial_activity", input_str=input_str)
    return f"processed:{input_str}"


@activity.defn
async def ping_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Echo activity returning received payload."""
    return {"status": "ok", "echo": payload}
