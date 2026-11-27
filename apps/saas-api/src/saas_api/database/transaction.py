from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


@asynccontextmanager
async def tenant_context(
    pool: AsyncConnectionPool,
    tenant_id: str | None,
) -> AsyncIterator[AsyncConnection[Any]]:
    """事务级租户上下文：SET LOCAL 在提交后自动还原，连接归还后不残留。"""
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE saas_app")
            await conn.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                [str(tenant_id) if tenant_id else ""],
            )
            await conn.execute(
                "SELECT set_config('app.scope', %s, true)",
                ["tenant" if tenant_id else "platform"],
            )
            yield conn
