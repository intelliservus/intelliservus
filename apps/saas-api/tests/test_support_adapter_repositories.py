from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from psycopg_pool import AsyncConnectionPool

from saas_api.modules.support_adapter.repositories import (
    OutboxRepository,
    SupportEventsRepository,
    WebhookDeliveriesRepository,
)
from support import fetch_one


async def test_delivery_insert_dedupes_on_unique_key(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    async with app_pool.connection() as conn:
        repo = WebhookDeliveriesRepository(conn)
        first = await repo.insert(
            provider="chatwoot",
            account_id="1",
            delivery_key="d-1",
            event_type="message_created",
            degraded=False,
        )
        second = await repo.insert(
            provider="chatwoot",
            account_id="1",
            delivery_key="d-1",
            event_type="message_created",
            degraded=False,
        )

    assert first is not None
    assert second is None
    counts = await fetch_one(
        admin_pool, "SELECT count(*) AS total FROM integration.webhook_deliveries"
    )
    assert counts == {"total": 1}


async def test_receive_transaction_rolls_back_every_row(
    app_pool: AsyncConnectionPool, admin_pool: AsyncConnectionPool, clean_db: None
) -> None:
    with pytest.raises(RuntimeError):
        async with app_pool.connection() as conn:
            async with conn.transaction():
                delivery_id = await WebhookDeliveriesRepository(conn).insert(
                    provider="chatwoot",
                    account_id="1",
                    delivery_key="d-rollback",
                    event_type="message_created",
                    degraded=False,
                )
                assert delivery_id is not None
                await SupportEventsRepository(conn).insert(
                    delivery_id=delivery_id,
                    event_type="conversation.message.received",
                    payload={},
                    status="received",
                    degraded=False,
                    trace_id="trace-1",
                    provider_created_at=None,
                )
                await OutboxRepository(conn).enqueue(
                    event_type="conversation.message.received",
                    payload={},
                    occurred_at=datetime.now(UTC),
                    trace_id="trace-1",
                )
                raise RuntimeError("boom")

    counts = await fetch_one(
        admin_pool,
        """
        SELECT (SELECT count(*) FROM integration.webhook_deliveries) AS deliveries,
               (SELECT count(*) FROM support.support_events) AS events,
               (SELECT count(*) FROM integration.outbox_events) AS outbox
        """,
    )
    assert counts == {"deliveries": 0, "events": 0, "outbox": 0}


async def test_claim_returns_earliest_available_event(
    app_pool: AsyncConnectionPool, clean_db: None
) -> None:
    now = datetime.now(UTC)
    async with app_pool.connection() as conn:
        async with conn.transaction():
            repo = OutboxRepository(conn)
            await repo.enqueue(
                event_type="conversation.message.received",
                payload={"n": "late"},
                occurred_at=now,
                trace_id="t",
                available_at=now - timedelta(minutes=1),
            )
            early = await repo.enqueue(
                event_type="conversation.message.received",
                payload={"n": "early"},
                occurred_at=now,
                trace_id="t",
                available_at=now - timedelta(hours=1),
            )

    async with app_pool.connection() as conn:
        async with conn.transaction():
            claimed = await OutboxRepository(conn).claim_one("worker-a")

    assert claimed is not None
    assert claimed.id == early
    assert claimed.attempt == 1


async def test_claim_skips_rows_locked_by_another_worker(
    app_pool: AsyncConnectionPool, clean_db: None
) -> None:
    now = datetime.now(UTC)
    async with app_pool.connection() as conn:
        async with conn.transaction():
            await OutboxRepository(conn).enqueue(
                event_type="conversation.message.received",
                payload={},
                occurred_at=now,
                trace_id="t",
            )

    async with app_pool.connection() as holder:
        async with holder.transaction():
            assert await OutboxRepository(holder).claim_one("worker-a") is not None
            async with app_pool.connection() as other:
                async with other.transaction():
                    assert await OutboxRepository(other).claim_one("worker-b") is None


async def test_concurrent_claims_do_not_double_deliver(
    app_pool: AsyncConnectionPool, clean_db: None
) -> None:
    now = datetime.now(UTC)
    async with app_pool.connection() as conn:
        async with conn.transaction():
            repo = OutboxRepository(conn)
            for index in range(2):
                await repo.enqueue(
                    event_type="conversation.message.received",
                    payload={"index": index},
                    occurred_at=now,
                    trace_id="t",
                )

    async def claim(worker: str) -> str | None:
        async with app_pool.connection() as conn:
            async with conn.transaction():
                event = await OutboxRepository(conn).claim_one(worker)
                return None if event is None else event.id

    claimed = await asyncio.gather(claim("worker-a"), claim("worker-b"))
    assert all(item is not None for item in claimed)
    assert len(set(claimed)) == 2
