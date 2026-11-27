from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace

TRACEPARENT = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True)
class RequestContext:
    trace_id: str
    span_id: str
    request_id: str
    tenant_id: str | None = None
    workspace_id: str | None = None
    user_id: str | None = None


_current: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def current_context() -> RequestContext | None:
    return _current.get()


def set_context(context: RequestContext) -> None:
    _current.set(context)


def update_identity(*, user_id: str | None, tenant_id: str | None) -> None:
    context = _current.get()
    if context is not None:
        _current.set(replace(context, user_id=user_id, tenant_id=tenant_id))


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    match = TRACEPARENT.match(value)
    if not match:
        return None
    trace_id = match.group(2)
    if trace_id == "0" * 32:
        return None
    return trace_id, match.group(3)


def build_context(headers: Mapping[str, str]) -> RequestContext:
    parsed = parse_traceparent(headers.get("traceparent"))
    request_id = headers.get("x-request-id") or str(uuid.uuid4())
    return RequestContext(
        trace_id=parsed[0] if parsed else uuid.uuid4().hex,
        span_id=parsed[1] if parsed else uuid.uuid4().hex[:16],
        request_id=request_id,
    )
