from __future__ import annotations

from typing import Any

from .request_context import current_context


def envelope(data: Any) -> dict[str, Any]:
    context = current_context()
    return {
        "data": data,
        "meta": {"request_id": context.request_id if context else ""},
    }


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    context = current_context()
    return {
        "error": {
            "code": code,
            "message": message,
            "details": {} if details is None else details,
            "retryable": False,
            "trace_id": context.trace_id if context else "",
        }
    }
