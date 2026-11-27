from __future__ import annotations

import asyncio
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from saas_api.database.transaction import tenant_context
from support import DSN, execute


@pytest.fixture
async def rls_data(admin_pool: AsyncConnectionPool, clean_db: None) -> tuple[Any, Any]:
    async with admin_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("INSERT INTO tenant.tenants (name) VALUES ('RLS A') RETURNING id")
            tenant_a = (await cur.fetchone())["id"]
            await cur.execute("INSERT INTO tenant.tenants (name) VALUES ('RLS B') RETURNING id")
            tenant_b = (await cur.fetchone())["id"]
            await cur.execute(
                "INSERT INTO tenant.workspaces (tenant_id, name) VALUES (%s, 'a-ws')", [tenant_a]
            )
            await cur.execute(
                "INSERT INTO tenant.workspaces (tenant_id, name) VALUES (%s, 'b-ws')", [tenant_b]
            )
    return tenant_a, tenant_b


async def test_without_context_sees_no_tenant_rows(
    raw_pool: AsyncConnectionPool, rls_data: tuple[Any, Any]
) -> None:
    async with raw_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM tenant.tenants")
            (count,) = await cur.fetchone()
    assert count == 0


async def test_tenant_context_sees_only_own_rows(
    raw_pool: AsyncConnectionPool, rls_data: tuple[Any, Any]
) -> None:
    tenant_a, _ = rls_data
    async with tenant_context(raw_pool, tenant_a) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM tenant.tenants")
            rows = await cur.fetchall()
    assert [str(row[0]) for row in rows] == [str(tenant_a)]


async def test_tenant_context_cannot_write_other_tenant(
    raw_pool: AsyncConnectionPool, rls_data: tuple[Any, Any]
) -> None:
    tenant_a, tenant_b = rls_data
    with pytest.raises(psycopg.Error, match="row-level security"):
        async with tenant_context(raw_pool, tenant_a) as conn:
            await conn.execute(
                "INSERT INTO tenant.workspaces (tenant_id, name) VALUES (%s, 'cross')", [tenant_b]
            )


async def test_platform_scope_sees_all_rows(
    raw_pool: AsyncConnectionPool, rls_data: tuple[Any, Any]
) -> None:
    async with tenant_context(raw_pool, None) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM tenant.tenants ORDER BY name")
            rows = await cur.fetchall()
    assert len(rows) == 2


async def test_no_residual_context_after_transaction(rls_data: tuple[Any, Any]) -> None:
    tenant_a, _ = rls_data
    pool = AsyncConnectionPool(DSN, open=False, min_size=1, max_size=1)
    await pool.open()
    try:
        async with tenant_context(pool, tenant_a):
            pass
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                (value,) = await cur.fetchone()
        assert (value or "") == ""
    finally:
        await pool.close()


async def test_concurrent_transactions_do_not_leak_tenants(
    raw_pool: AsyncConnectionPool, rls_data: tuple[Any, Any]
) -> None:
    tenant_a, tenant_b = rls_data

    async def one(index: int) -> tuple[str, str]:
        tenant_id = tenant_a if index % 2 == 0 else tenant_b
        async with tenant_context(raw_pool, tenant_id) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                (value,) = await cur.fetchone()
        return str(tenant_id), str(value)

    results = await asyncio.gather(*(one(index) for index in range(20)))
    for expected, actual in results:
        assert actual == expected


async def test_new_table_does_not_inherit_platform_bypass(
    admin_pool: AsyncConnectionPool,
    raw_pool: AsyncConnectionPool,
    rls_data: tuple[Any, Any],
) -> None:
    tenant_a, _ = rls_data
    try:
        await execute(admin_pool, "DROP TABLE IF EXISTS public.rls_probe")
        await execute(
            admin_pool,
            "CREATE TABLE public.rls_probe (id serial PRIMARY KEY, tenant_id uuid NOT NULL)",
        )
        await execute(admin_pool, "ALTER TABLE public.rls_probe ENABLE ROW LEVEL SECURITY")
        await execute(admin_pool, "ALTER TABLE public.rls_probe FORCE ROW LEVEL SECURITY")
        await execute(
            admin_pool,
            """
            CREATE POLICY tenant_only ON public.rls_probe
              FOR ALL
              USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
              WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """,
        )
        await execute(admin_pool, "GRANT SELECT, INSERT ON public.rls_probe TO saas_app")
        await execute(
            admin_pool, "GRANT USAGE, SELECT ON SEQUENCE public.rls_probe_id_seq TO saas_app"
        )

        async with tenant_context(raw_pool, tenant_a) as conn:
            await conn.execute("INSERT INTO public.rls_probe (tenant_id) VALUES (%s)", [tenant_a])

        async with tenant_context(raw_pool, None) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1 FROM public.rls_probe")
                rows = await cur.fetchall()
        assert len(rows) == 0
    finally:
        await execute(admin_pool, "DROP TABLE IF EXISTS public.rls_probe")
