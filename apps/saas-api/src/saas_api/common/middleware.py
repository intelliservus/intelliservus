from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logging import JsonLogger
from .request_context import build_context, set_context


class RequestContextMiddleware:
    """注入请求上下文（traceparent / request-id），并在响应完成后写一条访问日志。"""

    def __init__(self, app: ASGIApp, logger: JsonLogger) -> None:
        self._app = app
        self._logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        context = build_context(headers)
        set_context(context)

        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", context.request_id.encode("latin-1")))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            self._logger.info(
                "HTTP_REQUEST",
                "request completed",
                context,
                duration_ms=duration_ms,
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                status=status,
            )
