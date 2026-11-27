from __future__ import annotations

from typing import Any

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from support import fetch_one


async def test_ingress_role_can_append_ingress_rows(
    ingress_pool: AsyncConnectionPool,
    admin_pool: AsyncConnectionPool,
    clean_db: None,
) -> None:
    # 该角色没有 SELECT，因此写入不能带 RETURNING；读取由控制面角色完成。
    async with ingress_pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO integration.webhook_deliveries
              (provider, account_id, delivery_key, event_type)
            VALUES ('chatwoot', '1', 'delivery-1', 'message_created')
            """
        )

    delivery: dict[str, Any] | None = await fetch_one(
        admin_pool, "SELECT id FROM integration.webhook_deliveries"
    )
    assert delivery is not None

    async with ingress_pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO support.support_events (delivery_id, event_type, payload)
            VALUES (%s, 'conversation.message.received', '{}'::jsonb)
            """,
            [delivery["id"]],
        )
        await conn.execute(
            """
            INSERT INTO integration.outbox_events (event_type, occurred_at, payload)
            VALUES ('conversation.message.received', now(), '{}'::jsonb)
            """
        )

    counts = await fetch_one(
        admin_pool,
        """
        SELECT (SELECT count(*) FROM support.support_events) AS events,
               (SELECT count(*) FROM integration.outbox_events) AS outbox
        """,
    )
    assert counts == {"events": 1, "outbox": 1}


async def test_ingress_role_cannot_read_tenant_tables(
    ingress_pool: AsyncConnectionPool, clean_db: None
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with ingress_pool.connection() as conn:
            await conn.execute("SELECT count(*) FROM tenant.tenants")


async def test_ingress_role_cannot_read_its_own_tables(
    ingress_pool: AsyncConnectionPool, clean_db: None
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with ingress_pool.connection() as conn:
            await conn.execute("SELECT count(*) FROM support.support_events")
