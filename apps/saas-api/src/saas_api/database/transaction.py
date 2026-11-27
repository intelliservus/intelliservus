from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


@asynccontextmanager
async def ingress_context(
    pool: AsyncConnectionPool,
) -> AsyncIterator[AsyncConnection[Any]]:
    """公开 Ingress 的事务上下文：最小权限角色 + 无租户作用域。

    `app.scope = 'ingress'` 不匹配任何租户策略，配合 `saas_ingress` 只能追加
    接入侧表，保证端点被攻破时读不到业务数据（design D4）。
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE saas_ingress")
            await conn.execute("SELECT set_config('app.scope', 'ingress', true)")
            yield conn


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
