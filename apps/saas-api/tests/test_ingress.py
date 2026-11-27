from __future__ import annotations

import io
import json
import time
from typing import Any

import pytest
from psycopg_pool import AsyncConnectionPool

from saas_api.common.config import Settings
from saas_api.common.logging import JsonLogger
from saas_api.modules.ingress.service import IngressService
from saas_api.modules.ingress.signature import compute_signature
from saas_api.modules.support_adapter.repositories import OutboxRepository
from support import fetch_one

SECRET = "test-webhook-secret"
PATH = "/api/v1/ingress/chatwoot"

BASE_PAYLOAD: dict[str, Any] = {
    "event": "message_created",
    "id": 12,
    "content": "你好，我想查询订单状态",
    "message_type": "incoming",
    "private": False,
    "created_at": "2026-11-25T12:30:39.019Z",
    "content_type": "text",
    "source_id": "source-1",
    "account": {"id": 1, "name": "POC Workspace"},
    "inbox": {"id": 1, "name": "POC API Inbox"},
    "conversation": {
        "id": 5,
        "messages": [{"id": 1, "content": "history"}, {"id": 2, "content": "history"}],
        "meta": {"assignee": None},
    },
    "sender": {"id": 9, "type": "contact", "name": "客户"},
}


def signed(
    payload: dict[str, Any],
    *,
    secret: str = SECRET,
    timestamp: float | None = None,
    delivery: str | None = "delivery-1",
) -> tuple[dict[str, str], bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sent_at = str(int(time.time() if timestamp is None else timestamp))
    headers = {
        "content-type": "application/json",
        "x-chatwoot-timestamp": sent_at,
        "x-chatwoot-signature": compute_signature(secret, timestamp=sent_at, body=body),
    }
    if delivery is not None:
        headers["x-chatwoot-delivery"] = delivery
    return headers, body


async def _counts(pool: AsyncConnectionPool) -> dict[str, int]:
    result = await fetch_one(
        pool,
        """
        SELECT (SELECT count(*) FROM integration.webhook_deliveries) AS deliveries,
               (SELECT count(*) FROM support.support_events) AS events,
               (SELECT count(*) FROM integration.outbox_events) AS outbox
        """,
    )
    assert result is not None
    return result


async def test_accepts_signed_delivery(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD)

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "accepted", "eventType": "message_created"}
    assert await _counts(admin_pool) == {"deliveries": 1, "events": 1, "outbox": 1}

    event = await fetch_one(admin_pool, "SELECT payload, status FROM support.support_events")
    assert event is not None
    assert event["status"] == "received"
    payload = event["payload"]
    assert "conversation" not in payload
    assert payload["account_id"] == 1
    assert payload["conversation_id"] == 5
    assert payload["sender_type"] == "contact"


async def test_rejects_bad_signature(
    db_call: Any,
    admin_pool: AsyncConnectionPool,
    log_stream: io.StringIO,
    clean_db: None,
) -> None:
    headers, body = signed(BASE_PAYLOAD, secret="wrong-secret")

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    assert await _counts(admin_pool) == {"deliveries": 0, "events": 0, "outbox": 0}
    logs = log_stream.getvalue()
    assert SECRET not in logs
    assert "wrong-secret" not in logs
    assert headers["x-chatwoot-signature"] not in logs


async def test_rejects_stale_timestamp(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD, timestamp=time.time() - 301)

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_TIMESTAMP_INVALID"
    assert await _counts(admin_pool) == {"deliveries": 0, "events": 0, "outbox": 0}


async def test_rejects_missing_signature(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD)
    headers.pop("x-chatwoot-signature")

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"


async def test_rejects_missing_timestamp(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD)
    headers.pop("x-chatwoot-timestamp")

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_TIMESTAMP_INVALID"


async def test_rejects_oversized_body(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    response = await db_call(
        "POST",
        PATH,
        headers={"content-type": "application/json"},
        content=b"x" * (1024 * 1024 + 1),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "WEBHOOK_PAYLOAD_TOO_LARGE"
    assert await _counts(admin_pool) == {"deliveries": 0, "events": 0, "outbox": 0}


async def test_rejects_non_json_content_type(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD)
    headers["content-type"] = "text/plain"

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PARAM_INVALID"


async def test_rejects_invalid_json(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    body = b"{not json"
    timestamp = str(int(time.time()))
    headers = {
        "content-type": "application/json",
        "x-chatwoot-timestamp": timestamp,
        "x-chatwoot-signature": compute_signature(
            SECRET, timestamp=timestamp, body=body
        ),
        "x-chatwoot-delivery": "delivery-invalid-json",
    }

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PARAM_INVALID"
    assert await _counts(admin_pool) == {"deliveries": 0, "events": 0, "outbox": 0}


async def test_duplicate_delivery_is_idempotent(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD, delivery="delivery-dup")

    first = await db_call("POST", PATH, headers=headers, content=body)
    second = await db_call("POST", PATH, headers=headers, content=body)

    assert first.status_code == 200
    assert first.json()["data"]["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "duplicate"
    assert await _counts(admin_pool) == {"deliveries": 1, "events": 1, "outbox": 1}


async def test_missing_delivery_id_uses_degraded_composite_key(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    headers, body = signed(BASE_PAYLOAD, delivery=None)

    first = await db_call("POST", PATH, headers=headers, content=body)
    second = await db_call("POST", PATH, headers=headers, content=body)

    assert first.json()["data"]["status"] == "accepted"
    assert second.json()["data"]["status"] == "duplicate"
    delivery = await fetch_one(
        admin_pool, "SELECT delivery_key, degraded FROM integration.webhook_deliveries"
    )
    assert delivery is not None
    assert delivery["degraded"] is True
    assert delivery["delivery_key"].startswith("degraded:")


async def test_missing_delivery_id_on_update_event_is_not_deduped(
    db_call: Any, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    payload = {**BASE_PAYLOAD, "event": "message_updated"}
    headers, body = signed(payload, delivery=None)

    first = await db_call("POST", PATH, headers=headers, content=body)
    second = await db_call("POST", PATH, headers=headers, content=body)

    assert first.json()["data"]["status"] == "accepted"
    assert second.json()["data"]["status"] == "accepted"
    assert (await _counts(admin_pool))["deliveries"] == 2


async def test_receive_transaction_rolls_back_on_write_failure(
    app_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    settings: Settings,
    log_stream: io.StringIO,
    clean_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(self: OutboxRepository, **kwargs: Any) -> str:
        raise RuntimeError("outbox down")

    monkeypatch.setattr(OutboxRepository, "enqueue", boom)
    service = IngressService(app_pool, settings, JsonLogger("test", log_stream))
    headers, body = signed(BASE_PAYLOAD)

    with pytest.raises(RuntimeError):
        await service.receive(raw=body, headers=headers, trace_id="trace-rollback")

    assert await _counts(admin_pool) == {"deliveries": 0, "events": 0, "outbox": 0}
