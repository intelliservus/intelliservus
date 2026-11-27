from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...common.envelope import envelope
from ...common.errors import AppError
from ...common.request_context import current_context
from .service import IngressService

router = APIRouter()


@router.post("/ingress/chatwoot")
async def receive_chatwoot(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise AppError(400, "PARAM_INVALID", "content type must be application/json")

    raw = await _read_body(request, settings.webhook_max_body_bytes)
    context = current_context()
    service = IngressService(
        request.app.state.pool,
        settings,
        request.app.state.logger,
    )
    result = await service.receive(
        raw=raw,
        headers=request.headers,
        trace_id=context.trace_id if context else "",
    )
    return JSONResponse(
        status_code=200,
        content=envelope({"status": result.status, "eventType": result.event_type}),
    )


async def _read_body(request: Request, limit: int) -> bytes:
    """边读边计数，超限立即中止，避免把超大请求体读进内存。"""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise AppError(
                413,
                "WEBHOOK_PAYLOAD_TOO_LARGE",
                "request body exceeds limit",
                {"limit": limit},
            )
        chunks.append(chunk)
    return b"".join(chunks)
