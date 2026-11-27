from __future__ import annotations

import io
from typing import Any
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool

from saas_api.common.logging import JsonLogger
from saas_api.modules.support_adapter.mapping import (
    ChannelMapping,
    MappingResolver,
    UnmappedResolver,
    Unresolved,
)
from saas_api.modules.support_adapter.service import SupportAdapterService
from support import fetch_all, fetch_one, seed_support_event

BASE: dict[str, Any] = {
    "event": "message_created",
    "id": 12,
    "content": "我想查询订单",
    "message_type": "incoming",
    "private": False,
    "created_at": "2026-11-25T12:30:39.019Z",
    "account": {"id": 1},
    "inbox": {"id": 1},
    "conversation": {"id": 5},
    "sender": {"id": 9, "type": "contact"},
}


class StubResolver:
    def __init__(self, result: ChannelMapping | Unresolved) -> None:
        self._result = result
        self.calls: list[dict[str, str | None]] = []

    async def resolve(
        self,
        conn: Any,
        *,
        provider: str,
        account_id: str,
        inbox_id: str | None,
    ) -> ChannelMapping | Unresolved:
        self.calls.append({"account_id": account_id, "inbox_id": inbox_id})
        return self._result


def build_service(pool: AsyncConnectionPool, resolver: MappingResolver) -> SupportAdapterService:
    return SupportAdapterService(pool, resolver, JsonLogger("test", io.StringIO()))


async def test_unresolved_event_is_parked_without_downstream_rows(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    event = await seed_support_event(app_pool, BASE)
    service = build_service(app_pool, UnmappedResolver())

    outcome = await service.process(event)

    assert outcome == "pending_mapping"
    stored = await fetch_one(admin_pool, "SELECT status, tenant_id FROM support.support_events")
    assert stored == {"status": "pending_mapping", "tenant_id": None}
    assert await fetch_all(admin_pool, "SELECT 1 FROM support.messages") == []


async def test_resolved_event_persists_message_and_processing_record(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    event = await seed_support_event(app_pool, BASE)
    mapping = ChannelMapping(
        tenant_id=str(uuid4()), workspace_id=str(uuid4()), channel_id=None
    )
    resolver = StubResolver(mapping)
    service = build_service(app_pool, resolver)

    outcome = await service.process(event)

    assert outcome == "published"
    assert resolver.calls == [{"account_id": "1", "inbox_id": "1"}]
    stored = await fetch_one(
        admin_pool, "SELECT status, tenant_id, workspace_id FROM support.support_events"
    )
    assert stored is not None
    assert stored["status"] == "published"
    assert str(stored["tenant_id"]) == mapping.tenant_id
    assert str(stored["workspace_id"]) == mapping.workspace_id

    conversations = await fetch_all(admin_pool, "SELECT external_id FROM support.conversations")
    assert conversations == [{"external_id": "5"}]
    messages = await fetch_all(
        admin_pool, "SELECT external_id, direction FROM support.messages"
    )
    assert messages == [{"external_id": "12", "direction": "inbound"}]
    records = await fetch_all(
        admin_pool, "SELECT processing_type, status FROM integration.message_processing_records"
    )
    assert records == [{"processing_type": "agent_run", "status": "pending"}]


async def test_second_processing_is_skipped_as_duplicate(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    event = await seed_support_event(app_pool, BASE)
    mapping = ChannelMapping(
        tenant_id=str(uuid4()), workspace_id=str(uuid4()), channel_id=None
    )
    service = build_service(app_pool, StubResolver(mapping))

    first = await service.process(event)
    second = await service.process(event)

    assert first == "published"
    assert second == "skipped_duplicate"
    records = await fetch_all(
        admin_pool, "SELECT id FROM integration.message_processing_records"
    )
    assert len(records) == 1
    assert len(await fetch_all(admin_pool, "SELECT 1 FROM support.messages")) == 1


async def test_agent_bot_message_is_filtered_before_mapping(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    payload = {**BASE, "sender": {"id": 1, "type": "agent_bot"}, "message_type": "outgoing"}
    event = await seed_support_event(app_pool, payload)
    resolver = StubResolver(Unresolved("should not be called"))
    service = build_service(app_pool, resolver)

    outcome = await service.process(event)

    assert outcome == "filtered"
    assert resolver.calls == []
    stored = await fetch_one(admin_pool, "SELECT status FROM support.support_events")
    assert stored == {"status": "filtered"}
    assert await fetch_all(admin_pool, "SELECT 1 FROM support.messages") == []


async def test_payload_tenant_fields_are_ignored(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    payload = {**BASE, "tenant_id": "forged", "workspace_id": "forged"}
    event = await seed_support_event(app_pool, payload)
    mapping = ChannelMapping(
        tenant_id=str(uuid4()), workspace_id=str(uuid4()), channel_id=None
    )
    service = build_service(app_pool, StubResolver(mapping))

    await service.process(event)

    stored = await fetch_one(admin_pool, "SELECT tenant_id FROM support.support_events")
    assert stored is not None
    assert str(stored["tenant_id"]) == mapping.tenant_id
