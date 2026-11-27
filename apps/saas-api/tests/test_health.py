from __future__ import annotations

from conftest import Call


async def test_returns_data_meta_envelope(call: Call) -> None:
    response = await call("GET", "/api/v1/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"status": "ok"}
    assert body["meta"]["request_id"]
    assert response.headers["x-request-id"] == body["meta"]["request_id"]


async def test_reuses_incoming_request_id(call: Call) -> None:
    response = await call(
        "GET",
        "/api/v1/healthz",
        headers={"X-Request-Id": "incoming-request-id"},
    )

    assert response.json()["meta"]["request_id"] == "incoming-request-id"
