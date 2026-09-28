"""Request-scoped middleware for Agent Space backend.

Provides:
- Request ID generation and propagation (X-Request-ID header).
- Idempotency-Key enforcement for mutating API requests (M18).
- Request/response logging with timing.
"""

import asyncio
import hashlib
import time
import uuid

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.database import get_db_manager
from app.models.idempotency import IdempotencyRecord

logger = structlog.stdlib.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request and response.

    If the client sends an X-Request-ID header, it is reused; otherwise a
    new UUID4 is generated. The ID is stored on ``request.state.request_id``
    and echoed back on the response via the ``X-Request-ID`` header.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        # Bind request_id to structlog context for the duration of the request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.monotonic()

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Enforces request idempotency for mutating requests using Idempotency-Key header.

    Specifications:
    - Same key + same request payload: returns original cached response with Idempotent-Replayed: true.
    - Same key + different request payload: raises HTTP 409 IDEMPOTENCY_KEY_REUSED.
    - Concurrent duplicate requests: serialized safely, waiting for the in-flight request to complete.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get(
            "idempotency-key"
        )

        # Idempotency only applies to mutating requests with the header provided
        if not idempotency_key or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)

        try:
            db_manager = get_db_manager()
        except RuntimeError:
            return await call_next(request)

        body_bytes = await request.body()
        request_hash = hashlib.sha256(
            f"{request.method}:{request.url.path}:".encode() + body_bytes
        ).hexdigest()

        # Step 1: Check existing record
        async with db_manager.session_factory() as session:
            stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

        if record:
            if record.status == "COMPLETED":
                if record.request_hash == request_hash:
                    headers = dict(record.response_headers or {})
                    headers["Idempotent-Replayed"] = "true"
                    headers["Idempotency-Key"] = idempotency_key
                    return Response(
                        content=record.response_body or "",
                        status_code=record.response_status_code or 200,
                        media_type="application/json",
                        headers=headers,
                    )
                else:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "code": "IDEMPOTENCY_KEY_REUSED",
                            "message": "The provided Idempotency-Key has already been used with a different request payload.",
                            "details": {"key": idempotency_key},
                            "request_id": getattr(request.state, "request_id", ""),
                        },
                    )
            elif record.status == "PROCESSING":
                if record.request_hash != request_hash:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "code": "IDEMPOTENCY_KEY_REUSED",
                            "message": "The provided Idempotency-Key has already been used with a different request payload.",
                            "details": {"key": idempotency_key},
                            "request_id": getattr(request.state, "request_id", ""),
                        },
                    )

                # Wait for in-flight request to finish
                for _ in range(40):
                    await asyncio.sleep(0.05)
                    async with db_manager.session_factory() as poll_session:
                        stmt = select(IdempotencyRecord).where(
                            IdempotencyRecord.key == idempotency_key
                        )
                        res = await poll_session.execute(stmt)
                        rec = res.scalar_one_or_none()
                        if rec and rec.status == "COMPLETED":
                            headers = dict(rec.response_headers or {})
                            headers["Idempotent-Replayed"] = "true"
                            headers["Idempotency-Key"] = idempotency_key
                            return Response(
                                content=rec.response_body or "",
                                status_code=rec.response_status_code or 200,
                                media_type="application/json",
                                headers=headers,
                            )

        # Step 2: Insert new PROCESSING record
        inserted = False
        async with db_manager.session_factory() as session:
            new_rec = IdempotencyRecord(
                key=idempotency_key,
                request_hash=request_hash,
                request_method=request.method,
                request_path=request.url.path,
                status="PROCESSING",
            )
            session.add(new_rec)
            try:
                await session.commit()
                inserted = True
            except IntegrityError:
                await session.rollback()

        if not inserted:
            # Another concurrent request inserted first: poll for its result
            async with db_manager.session_factory() as recheck_session:
                stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key)
                res = await recheck_session.execute(stmt)
                rec = res.scalar_one_or_none()
                if rec and rec.request_hash != request_hash:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "code": "IDEMPOTENCY_KEY_REUSED",
                            "message": "The provided Idempotency-Key has already been used with a different request payload.",
                            "details": {"key": idempotency_key},
                            "request_id": getattr(request.state, "request_id", ""),
                        },
                    )

            for _ in range(40):
                await asyncio.sleep(0.05)
                async with db_manager.session_factory() as p_session:
                    stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key)
                    res = await p_session.execute(stmt)
                    p_rec = res.scalar_one_or_none()
                    if p_rec and p_rec.status == "COMPLETED":
                        headers = dict(p_rec.response_headers or {})
                        headers["Idempotent-Replayed"] = "true"
                        headers["Idempotency-Key"] = idempotency_key
                        return Response(
                            content=p_rec.response_body or "",
                            status_code=p_rec.response_status_code or 200,
                            media_type="application/json",
                            headers=headers,
                        )

        # Step 3: Execute request
        try:
            response = await call_next(request)
            chunks = [chunk async for chunk in response.body_iterator]
            response_body = b"".join(chunks)

            # Mark COMPLETED with response payload
            async with db_manager.session_factory() as update_session:
                stmt = (
                    update(IdempotencyRecord)
                    .where(IdempotencyRecord.key == idempotency_key)
                    .values(
                        status="COMPLETED",
                        response_status_code=response.status_code,
                        response_headers={
                            k: v
                            for k, v in response.headers.items()
                            if k.lower() in {"content-type"}
                        },
                        response_body=response_body.decode("utf-8", errors="replace"),
                    )
                )
                await update_session.execute(stmt)
                await update_session.commit()

            resp_headers = dict(response.headers)
            resp_headers["Idempotent-Replayed"] = "false"
            resp_headers["Idempotency-Key"] = idempotency_key
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=resp_headers,
                media_type=response.media_type,
            )
        except Exception:
            # Clean up aborted processing record on uncaught failure
            try:
                async with db_manager.session_factory() as cleanup_session:
                    stmt = delete(IdempotencyRecord).where(
                        IdempotencyRecord.key == idempotency_key,
                        IdempotencyRecord.status == "PROCESSING",
                    )
                    await cleanup_session.execute(stmt)
                    await cleanup_session.commit()
            except Exception:
                pass
            raise
