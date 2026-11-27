from __future__ import annotations

import io
import json
import re
from typing import Any

from conftest import Call

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


def _records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def _request_record(stream: io.StringIO) -> dict[str, Any]:
    return next(record for record in _records(stream) if record.get("code") == "HTTP_REQUEST")


async def test_reuses_incoming_traceparent_and_request_id(
    call: Call, log_stream: io.StringIO
) -> None:
    response = await call(
        "GET",
        "/api/v1/healthz",
        headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01", "X-Request-Id": "req-123"},
    )

    assert response.headers["x-request-id"] == "req-123"

    record = _request_record(log_stream)
    assert record["service"] == "saas-api"
    assert record["trace_id"] == TRACE_ID
    assert record["span_id"] == SPAN_ID
    assert record["request_id"] == "req-123"
    assert isinstance(record["duration_ms"], (int, float))


async def test_generates_trace_when_traceparent_missing(
    call: Call, log_stream: io.StringIO
) -> None:
    await call("GET", "/api/v1/healthz")

    record = _request_record(log_stream)
    assert re.fullmatch(r"[0-9a-f]{32}", record["trace_id"])
    assert re.fullmatch(r"[0-9a-f]{16}", record["span_id"])


async def test_does_not_log_credentials_or_request_body(
    call: Call, log_stream: io.StringIO
) -> None:
    await call(
        "POST",
        "/api/v1/healthz",
        headers={"Authorization": "Bearer super-secret-token"},
        json={"password": "hunter2"},
    )

    _request_record(log_stream)
    joined = log_stream.getvalue()
    assert "super-secret-token" not in joined
    assert "hunter2" not in joined
    assert "authorization" not in joined.lower()
    assert "password" not in joined.lower()
