from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

import pytest
from psycopg_pool import AsyncConnectionPool

from saas_api.common.logging import JsonLogger
from saas_api.modules.ingress.signature import compute_signature
from saas_api.modules.support_adapter.mapping import UnmappedResolver
from saas_api.modules.support_adapter.repositories import OutboxEvent
from saas_api.modules.support_adapter.service import SupportAdapterService
from support import fetch_one

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "chatwoot-4.20.1"
SECRET = "test-webhook-secret"
PATH = "/api/v1/ingress/chatwoot"

FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))

# 上游真实样本 → 消费侧应得到的终态（design D9、事实源 §5.8）。
EXPECTED_OUTCOME = {
    "message_created": "filtered",
    "message_updated": "filtered",
    "message_created_agent_bot": "filtered",
    "message_created_private": "filtered",
    "message_created_customer": "pending_mapping",
    "conversation_created": "pending_mapping",
    "conversation_updated": "pending_mapping",
    "conversation_status_changed": "pending_mapping",
    "contact_created": "pending_mapping",
    "contact_updated": "pending_mapping",
}


def test_every_fixture_has_an_expected_outcome() -> None:
    assert {path.stem for path in FIXTURES} == set(EXPECTED_OUTCOME)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
async def test_replay_fixture(
    fixture: Path,
    db_call: Any,
    app_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    clean_db: None,
) -> None:
    record = json.loads(fixture.read_text(encoding="utf-8"))
    body = json.dumps(record["payload"], ensure_ascii=False).encode("utf-8")
    sent_at = str(int(time.time()))
    headers = {
        "content-type": "application/json",
        "x-chatwoot-timestamp": sent_at,
        "x-chatwoot-signature": compute_signature(SECRET, timestamp=sent_at, body=body),
        "x-chatwoot-delivery": f"fixture-{fixture.stem}",
    }

    response = await db_call("POST", PATH, headers=headers, content=body)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "accepted"

    stored = await fetch_one(
        admin_pool,
        "SELECT id, payload, event_type FROM support.support_events",
    )
    assert stored is not None
    assert stored["event_type"] == record["event"]
    projected = stored["payload"]
    assert "conversation" not in projected
    assert "messages" not in projected
    assert "request_headers" not in projected

    outbox = await fetch_one(admin_pool, "SELECT id FROM integration.outbox_events")
    assert outbox is not None
    event = OutboxEvent(
        id=str(outbox["id"]),
        event_type="support.event.received",
        schema_version=1,
        tenant_id=None,
        workspace_id=None,
        trace_id="contract",
        attempt=1,
        retry_of=None,
        payload={"support_event_id": str(stored["id"])},
    )
    service = SupportAdapterService(
        app_pool, UnmappedResolver(), JsonLogger("contract", io.StringIO())
    )

    outcome = await service.process(event)

    assert outcome == EXPECTED_OUTCOME[fixture.stem]
    final = await fetch_one(admin_pool, "SELECT status FROM support.support_events")
    assert final is not None
    assert final["status"] == outcome
