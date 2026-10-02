"""WebSocket Realtime Gateway for Agent Space.

Endpoint:
    WS /api/v1/ws/projects/{project_id}

Authorizes connection before accepting subscription.
Dispatches real-time events for:
- task.updated
- task.assigned
- task.released
- agent.status
- artifact.created
- workflow.updated
- human.input_required

Note: PostgreSQL state remains strictly authoritative. Frontend clients
must recover via REST if events are missed (e.g. on reconnection).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.auth.oidc import get_oidc_client
from app.database import get_db_manager
from app.models.task import Task
from app.repositories.project_member_repo import ProjectMemberRepository
from app.repositories.project_repo import ProjectRepository
from app.services.user_service import reconcile_user

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter()

SUPPORTED_EVENT_TYPES = {
    "task.snapshot",
    "task.deleted",
    "task.updated",
    "task.assigned",
    "task.released",
    "agent.status",
    "artifact.created",
    "workflow.updated",
    "human.input_required",
}


async def _stream_task_snapshots(websocket: WebSocket, project_id: uuid.UUID) -> None:
    """Stream authoritative task changes regardless of which worker changed them."""
    versions: dict[uuid.UUID, tuple[int, str]] = {}
    db_mgr = get_db_manager()
    while True:
        async with db_mgr.session_factory() as session:
            tasks = list(
                (
                    await session.scalars(
                        select(Task)
                        .where(Task.project_id == project_id)
                        .order_by(Task.created_at.asc())
                    )
                ).all()
            )
        current_ids = {task.id for task in tasks}
        for task in tasks:
            marker = (task.version, task.updated_at.isoformat())
            if versions.get(task.id) == marker:
                continue
            versions[task.id] = marker
            await websocket.send_json(
                {
                    "event": "task.snapshot",
                    "project_id": str(project_id),
                    "payload": {
                        "id": str(task.id),
                        "project_id": str(task.project_id),
                        "organization_id": str(task.organization_id),
                        "title": task.title,
                        "description": task.description,
                        "status": task.status,
                        "priority": task.priority,
                        "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
                        "assigned_user_id": str(task.assigned_user_id) if task.assigned_user_id else None,
                        "version": task.version,
                        "context": task.context,
                        "result": task.result,
                        "error_message": task.error_message,
                        "created_at": task.created_at.isoformat(),
                        "updated_at": task.updated_at.isoformat(),
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        for removed_id in set(versions) - current_ids:
            del versions[removed_id]
            await websocket.send_json(
                {
                    "event": "task.deleted",
                    "project_id": str(project_id),
                    "payload": {"id": str(removed_id)},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        await asyncio.sleep(1)


class ConnectionManager:
    """Manages active WebSocket connections grouped by project ID."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, project_id: uuid.UUID, websocket: WebSocket) -> None:
        """Accept WebSocket connection and register in project pool."""
        await websocket.accept()
        async with self._lock:
            if project_id not in self._connections:
                self._connections[project_id] = set()
            self._connections[project_id].add(websocket)
        logger.info("websocket_connected", project_id=str(project_id))

    def disconnect(self, project_id: uuid.UUID, websocket: WebSocket) -> None:
        """Remove WebSocket connection from project pool."""
        if project_id in self._connections:
            self._connections[project_id].discard(websocket)
            if not self._connections[project_id]:
                del self._connections[project_id]
        logger.info("websocket_disconnected", project_id=str(project_id))

    async def broadcast_to_project(
        self,
        project_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        """Broadcast domain event to all clients connected to project_id.

        Returns number of clients successfully notified.
        """
        async with self._lock:
            sockets = list(self._connections.get(project_id, []))

        if not sockets:
            return 0

        message = {
            "event": event_type,
            "project_id": str(project_id),
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        sent = 0
        dead_sockets: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                dead_sockets.append(ws)

        for ws in dead_sockets:
            self.disconnect(project_id, ws)

        return sent

    def active_connection_count(self, project_id: uuid.UUID) -> int:
        """Return number of active connections for a project."""
        return len(self._connections.get(project_id, set()))


_connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Return singleton WebSocket connection manager."""
    return _connection_manager


@router.websocket("/ws/projects/{project_id}")
async def project_websocket_endpoint(
    websocket: WebSocket,
    project_id: uuid.UUID,
    token: str | None = Query(default=None),
) -> None:
    """Real-time project event gateway.

    Authorizes client token and project membership before accepting subscription.
    """
    manager = get_connection_manager()

    # 1. Extract Bearer token from query parameter or Authorization header
    raw_token = token
    if not raw_token:
        auth_header = websocket.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        logger.warning("websocket_missing_token", project_id=str(project_id))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return

    # 2. Verify token signature and claims
    oidc = get_oidc_client()
    try:
        claims = oidc.verify_token(raw_token)
        user = oidc.claims_to_user(claims)
    except Exception as exc:
        logger.warning("websocket_invalid_token", error=str(exc))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        return

    # 3. Verify user membership in project
    db_mgr = get_db_manager()
    async with db_mgr.session_factory() as session:
        db_user = await reconcile_user(session, user)

        # Check project existence
        proj_repo = ProjectRepository(session)
        proj = await proj_repo.get_by_id(project_id)
        if not proj:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Project not found")
            return

        # Check project membership or org admin
        is_org_admin = db_user.role == "ORG_ADMIN" and db_user.organization_id == proj.organization_id
        member_repo = ProjectMemberRepository(session)
        member = await member_repo.get_by_project_and_user(project_id, db_user.id)

        if not member and not is_org_admin:
            logger.warning(
                "websocket_unauthorized_member",
                user_id=str(db_user.id),
                project_id=str(project_id),
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized for project")
            return

    # 4. Accept authorized connection
    await manager.connect(project_id, websocket)

    # 5. Send initial connection established acknowledgment
    await websocket.send_json(
        {
            "event": "connection.established",
            "project_id": str(project_id),
            "user_id": str(db_user.id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # 6. Listen for incoming client messages (heartbeat/ping)
    stream_task = asyncio.create_task(_stream_task_snapshots(websocket, project_id))
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("action") == "ping":
                await websocket.send_json({"event": "pong", "timestamp": datetime.now(UTC).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
    except Exception as exc:
        logger.debug("websocket_exception_closed", error=str(exc))
        manager.disconnect(project_id, websocket)
    finally:
        stream_task.cancel()
        await asyncio.gather(stream_task, return_exceptions=True)
