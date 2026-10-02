"""Durable default-agent execution against the shared project workspace."""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from temporalio import activity

from app.config import get_settings
from app.database import get_db_manager
from app.models.agent import Agent
from app.models.project import Project
from app.models.task import Task
from app.repositories.outbox_repo import OutboxRepository
from app.services import workspace


def _json_object(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I))
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Agent returned an invalid response")
    return value


async def _gemini(prompt: str, *, system_prompt: str | None = None, max_tokens: int = 8192) -> str:
    settings = get_settings()
    key = settings.default_gemini_api_key
    if not key or not key.get_secret_value().strip():
        raise RuntimeError("DEFAULT_GEMINI_API_KEY is required for the default agent")
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"},
    }
    if system_prompt:
        body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{settings.gemini_api_base_url.rstrip('/')}/models/{settings.default_agent_model}:generateContent",
            headers={"x-goog-api-key": key.get_secret_value()},
            json=body,
        )
    response.raise_for_status()
    return "".join(
        part.get("text", "")
        for part in response.json()["candidates"][0]["content"]["parts"]
    )


async def _stage(task_id: uuid.UUID, agent_id: uuid.UUID, label: str, *, status: str | None = None, extra: dict[str, Any] | None = None) -> None:
    db = get_db_manager()
    async with db.session_factory() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None or task.assigned_agent_id != agent_id or task.status not in {"CLAIMED", "IN_PROGRESS"}:
            raise RuntimeError("Task assignment changed while the default agent was working")
        if status:
            task.status = status
        task.result = {"stage": label, **(extra or {})}
        task.version += 1
        await session.commit()


@activity.defn
async def execute_default_agent_task(payload: dict[str, str]) -> dict[str, Any]:
    """Ask Gemini to choose files and write complete contents, then checkpoint for review."""
    task_id = uuid.UUID(payload["task_id"])
    agent_id = uuid.UUID(payload["agent_id"])
    db = get_db_manager()
    async with db.session_factory() as session:
        task = await session.get(Task, task_id)
        agent = await session.get(Agent, agent_id)
        if task is None or agent is None or task.assigned_agent_id != agent.id or task.organization_id != agent.organization_id:
            raise RuntimeError("Assigned task or agent is unavailable")
        if agent.model_provider != "default":
            raise RuntimeError("User-key agents must execute in the browser")
        if task.status == "REVIEW" and task.result:
            return dict(task.result)
        if task.status != "CLAIMED":
            raise RuntimeError(f"Task cannot start from {task.status}")
        project = await session.get(Project, task.project_id)
        if project is None:
            raise RuntimeError("Project no longer exists")
        project_id = project.id
        project_name = project.name
        project_brief = project.description or ""
        task_title = task.title
        task_description = task.description or ""
        suggested = task.context.get("suggested_files", []) if isinstance(task.context, dict) else []
        system_prompt = agent.system_prompt

    await _stage(task_id, agent_id, "Planner selecting files", status="IN_PROGRESS")
    activity.heartbeat("planning")
    listing = await asyncio.to_thread(workspace.list_files, project_id)
    existing = {str(entry["path"]): int(entry["size"]) for entry in listing}
    plan_prompt = (
        "You are the project planner. Choose up to 12 project-relative files for the assigned task. "
        'Return JSON only: {"instructions":"...","files":["relative/path"]}.\n'
        f"Project: {project_name}\nBrief: {project_brief}\nTask: {task_title}\n"
        f"Description: {task_description}\nSuggested: {suggested}\nExisting: {list(existing)}"
    )
    plan = _json_object(await _gemini(plan_prompt, max_tokens=2048))
    selected = list(dict.fromkeys(path for path in plan.get("files", []) if isinstance(path, str)))[:12]
    if not selected:
        raise ValueError("Planner selected no files")
    for path in selected:
        workspace.file_path(project_id, path)
    await _stage(task_id, agent_id, "Agent writing files", extra={"files": selected})
    activity.heartbeat("generating")

    snapshots: dict[str, str] = {}
    context = (
        f"Project: {project_name}\nBrief: {project_brief}\nTask: {task_title}\n"
        f"Description: {task_description}\nPlanner instructions: {plan.get('instructions', '')}\n"
        f"Files assigned: {selected}\n"
    )
    budget = 60000
    for path in selected:
        size = existing.get(path)
        if size is None or size > 20000 or size > budget:
            continue
        content = await asyncio.to_thread(workspace.read_file, project_id, path)
        snapshots[path] = content
        context += f"\n--- {path} ---\n{content}\n"
        budget -= size
    context += (
        '\nReturn JSON only: {"summary":"what changed","files":[{"path":"relative/path",'
        '"content":"complete new UTF-8 file content"}]}. Change only assigned files.'
    )
    generated = _json_object(await _gemini(context, system_prompt=system_prompt, max_tokens=16384))
    files = generated.get("files")
    if not isinstance(files, list) or not files or any(
        not isinstance(item, dict)
        or item.get("path") not in selected
        or not isinstance(item.get("content"), str)
        or len(item["content"].encode()) > workspace.MAX_FILE_BYTES
        for item in files
    ):
        raise ValueError("Agent returned invalid changes")
    paths = [item["path"] for item in files]
    if len(paths) != len(set(paths)):
        raise ValueError("Agent returned duplicate file paths")

    changes = []
    for item in files:
        before = snapshots.get(item["path"], "").splitlines()
        after = item["content"].splitlines()
        diff = list(difflib.ndiff(before, after))
        changes.append(
            {
                "path": item["path"],
                "additions": sum(line.startswith("+ ") for line in diff),
                "deletions": sum(line.startswith("- ") for line in diff),
            }
        )

    # Check every target before the first write so a human edit cannot leave a
    # partially applied multi-file response.
    for path in paths:
        target = workspace.file_path(project_id, path)
        if path in snapshots:
            current = await asyncio.to_thread(workspace.read_file, project_id, path)
            if current != snapshots[path]:
                raise RuntimeError(f"{path} changed during agent work; review and retry")
        elif target.exists():
            raise RuntimeError(f"{path} was created during agent work; review and retry")

    await _stage(
        task_id,
        agent_id,
        "Applying shared edits",
        extra={"files": paths, "changes": changes},
    )
    activity.heartbeat("applying")
    for index, item in enumerate(files):
        path = item["path"]
        await _stage(
            task_id,
            agent_id,
            f"Applying {path} ({index + 1}/{len(files)})",
            extra={"files": paths, "changes": changes, "active_file": path},
        )
        if path in snapshots:
            await asyncio.to_thread(workspace.write_file, project_id, path, item["content"])
        else:
            await asyncio.to_thread(workspace.write_file, project_id, path, item["content"], create_only=True)
    checkpoint = await asyncio.to_thread(workspace.checkpoint, project_id, f"Agent task: {task_title}", "Default Gemini Agent")
    summary = str(generated.get("summary") or "Changes applied")[:2048]
    result = {
        "stage": "Ready for review",
        "summary": summary,
        "files": paths,
        "changes": changes,
        "commit": checkpoint["commit"],
    }
    async with db.session_factory() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None or task.assigned_agent_id != agent_id or task.status != "IN_PROGRESS":
            raise RuntimeError("Task assignment changed before review")
        task.status = "REVIEW"
        task.result = result
        task.error_message = None
        task.version += 1
        await OutboxRepository(session).record_event(
            event_type="task.transitioned", aggregate_type="task", aggregate_id=task.id,
            payload={"task_id": str(task.id), "new_status": "REVIEW", "files": paths},
            organization_id=task.organization_id, project_id=task.project_id,
        )
        await session.commit()
    return result


@activity.defn
async def fail_default_agent_task(payload: dict[str, str]) -> None:
    """Expose worker failures on the task board without leaking provider keys."""
    task_id = uuid.UUID(payload["task_id"])
    db = get_db_manager()
    async with db.session_factory() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if (
            task
            and task.assigned_agent_id == uuid.UUID(payload["agent_id"])
            and task.status in {"CLAIMED", "IN_PROGRESS"}
        ):
            task.status = "FAILED"
            task.error_message = payload.get("error", "Agent work failed")[:2048]
            task.result = {"stage": "Needs attention"}
            task.version += 1
            await session.commit()
