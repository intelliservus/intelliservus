from __future__ import annotations

import os
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from httpx import Response
from psycopg.rows import dict_row

from saas_api.modules.iam.permissions import AGENT_PERMISSIONS, TENANT_ADMIN_PERMISSIONS
from saas_api.modules.support_adapter.events import project_event
from saas_api.modules.support_adapter.repositories import (
    OutboxEvent,
    OutboxRepository,
    SupportEventsRepository,
    WebhookDeliveriesRepository,
)

DSN = os.environ.get("TEST_DATABASE_URL", "")
ORIGIN = "http://localhost:8080"
PASSWORD = "correct-horse-battery"

Call = Callable[..., Awaitable[Response]]

TRUNCATE_SQL = """
TRUNCATE integration.message_processing_records, support.messages, support.conversations,
         support.support_events, integration.outbox_events, integration.webhook_deliveries,
         audit.audit_logs, iam.refresh_tokens, iam.memberships, iam.role_permissions,
         iam.roles, tenant.workspaces, tenant.tenants, iam.users
RESTART IDENTITY CASCADE
"""


async def truncate(pool: Any) -> None:
    async with pool.connection() as conn:
        await conn.execute(TRUNCATE_SQL)


async def fetch_all(pool: Any, sql: str, params: Any = None) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params or ())
            return await cur.fetchall()


async def fetch_one(pool: Any, sql: str, params: Any = None) -> dict[str, Any] | None:
    rows = await fetch_all(pool, sql, params)
    return rows[0] if rows else None


async def execute(pool: Any, sql: str, params: Any = None) -> None:
    async with pool.connection() as conn:
        await conn.execute(sql, params or ())


async def insert_returning(pool: Any, sql: str, params: Any = None) -> Any:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params or ())
            row = await cur.fetchone()
            return row[0] if row else None


def cookie_header(response: Any, name: str = "refresh_token") -> str:
    raw = response.headers.get("set-cookie", "")
    match = re.search(rf"{name}=([^;,\s]+)", raw)
    if not match:
        raise AssertionError(f"no {name} cookie in {raw!r}")
    return f"{name}={match.group(1)}"


async def create_user(
    pool: Any,
    password_hash: str,
    email: str,
    *,
    platform_admin: bool = False,
    disabled: bool = False,
) -> str:
    user_id = await insert_returning(
        pool,
        """
        INSERT INTO iam.users (email, display_name, password_hash, status, is_platform_admin)
        VALUES (lower(%s), 'Test User', %s, %s, %s) RETURNING id
        """,
        [email, password_hash, "disabled" if disabled else "active", platform_admin],
    )
    return str(user_id)


async def create_tenant(
    pool: Any,
    name: str,
    *,
    suffixes: tuple[str, ...] = ("a", "b"),
    workspace_name: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    tenant_id = await insert_returning(
        pool, "INSERT INTO tenant.tenants (name) VALUES (%s) RETURNING id", [name]
    )

    workspace_ids: list[str] = []
    for suffix in suffixes:
        label = workspace_name(suffix) if workspace_name else f"{name}-{suffix}"
        workspace_id = await insert_returning(
            pool,
            "INSERT INTO tenant.workspaces (tenant_id, name) VALUES (%s, %s) RETURNING id",
            [tenant_id, label],
        )
        workspace_ids.append(str(workspace_id))

    admin_role_id = await insert_returning(
        pool,
        "INSERT INTO iam.roles (tenant_id, name) VALUES (%s, 'tenant_admin') RETURNING id",
        [tenant_id],
    )
    for permission in TENANT_ADMIN_PERMISSIONS:
        await execute(
            pool,
            """
            INSERT INTO iam.role_permissions (role_id, permission_key)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            [admin_role_id, permission],
        )

    agent_role_id = await insert_returning(
        pool,
        "INSERT INTO iam.roles (tenant_id, name) VALUES (%s, 'agent') RETURNING id",
        [tenant_id],
    )
    for permission in AGENT_PERMISSIONS:
        await execute(
            pool,
            """
            INSERT INTO iam.role_permissions (role_id, permission_key)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            [agent_role_id, permission],
        )

    return {
        "tenant_id": str(tenant_id),
        "workspace_ids": workspace_ids,
        "admin_role_id": str(admin_role_id),
        "agent_role_id": str(agent_role_id),
    }


async def add_membership(
    pool: Any,
    *,
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    role_id: str,
) -> None:
    await execute(
        pool,
        """
        INSERT INTO iam.memberships (tenant_id, workspace_id, user_id, role_id)
        VALUES (%s, %s, %s, %s)
        """,
        [tenant_id, workspace_id, user_id, role_id],
    )


async def login(call: Any, email: str, password: str = PASSWORD) -> Any:
    return await call(
        "POST",
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": email, "password": password},
    )


async def login_as(call: Any, email: str, password: str = PASSWORD) -> str:
    response = await login(call, email, password)
    if response.status_code != 200:
        raise AssertionError(f"login failed ({response.status_code}): {response.text}")
    return token_of(response)


def token_of(response: Any) -> str:
    return str(response.json()["data"]["access_token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def vendor_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    payload.update(overrides)
    return payload


async def seed_support_event(
    pool: Any,
    payload: dict[str, Any],
    *,
    trace_id: str = "trace-1",
    provider_created_at: datetime | None = None,
) -> OutboxEvent:
    """按接收事务的顺序写入投递、事件与 outbox，返回可被 Worker 领取的事件。"""
    async with pool.connection() as conn:
        async with conn.transaction():
            delivery_id = await WebhookDeliveriesRepository(conn).insert(
                provider="chatwoot",
                account_id=str((payload.get("account") or {}).get("id")),
                delivery_key=f"delivery-{uuid.uuid4()}",
                event_type=str(payload.get("event")),
                degraded=False,
            )
            assert delivery_id is not None
            support_event_id = await SupportEventsRepository(conn).insert(
                delivery_id=delivery_id,
                event_type=str(payload.get("event")),
                payload=project_event(payload),
                status="received",
                degraded=False,
                trace_id=trace_id,
                provider_created_at=provider_created_at,
            )
            outbox_id = await OutboxRepository(conn).enqueue(
                event_type="support.event.received",
                payload={
                    "support_event_id": support_event_id,
                    "delivery_id": delivery_id,
                },
                occurred_at=datetime.now(UTC),
                trace_id=trace_id,
            )
    return OutboxEvent(
        id=outbox_id,
        event_type="support.event.received",
        schema_version=1,
        tenant_id=None,
        workspace_id=None,
        trace_id=trace_id,
        attempt=1,
        retry_of=None,
        payload={"support_event_id": support_event_id, "delivery_id": delivery_id},
    )
