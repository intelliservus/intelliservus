from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...database.repository import Repository


@dataclass(frozen=True)
class OutboxEvent:
    id: str
    event_type: str
    schema_version: int
    tenant_id: str | None
    workspace_id: str | None
    trace_id: str
    attempt: int
    retry_of: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class SupportEventRecord:
    id: str
    event_type: str
    payload: dict[str, Any]
    status: str
    provider_created_at: datetime | None
    tenant_id: str | None
    workspace_id: str | None
    trace_id: str
    degraded: bool


class WebhookDeliveriesRepository(Repository):
    """投递记录。INSERT 由 Ingress 角色执行——该角色没有 SELECT，故不使用 RETURNING。"""

    async def insert(
        self,
        *,
        provider: str,
        account_id: str,
        delivery_key: str,
        event_type: str | None,
        degraded: bool,
    ) -> str | None:
        delivery_id = str(uuid4())
        async with self.conn.cursor() as cur:
            # 不写冲突目标：指定目标要求该表的 SELECT 权限，而 Ingress 角色刻意没有。
            await cur.execute(
                """
                INSERT INTO integration.webhook_deliveries
                  (id, provider, account_id, delivery_key, event_type, degraded)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                [delivery_id, provider, account_id, delivery_key, event_type, degraded],
            )
            inserted = cur.rowcount == 1
        return delivery_id if inserted else None


class SupportEventsRepository(Repository):
    async def insert(
        self,
        *,
        delivery_id: str,
        event_type: str,
        payload: dict[str, Any],
        status: str,
        degraded: bool,
        trace_id: str,
        provider_created_at: datetime | None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        event_id = str(uuid4())
        await self.conn.execute(
            """
            INSERT INTO support.support_events
              (id, delivery_id, tenant_id, workspace_id, event_type,
               provider_created_at, payload, status, degraded, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                event_id,
                delivery_id,
                tenant_id,
                workspace_id,
                event_type,
                provider_created_at,
                Jsonb(payload),
                status,
                degraded,
                trace_id,
            ],
        )
        return event_id

    async def find(self, event_id: str) -> SupportEventRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, event_type, payload, status, provider_created_at,
                       tenant_id, workspace_id, trace_id, degraded
                  FROM support.support_events
                 WHERE id = %s
                """,
                [event_id],
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return SupportEventRecord(
            id=str(row["id"]),
            event_type=str(row["event_type"]),
            payload=dict(row["payload"]),
            status=str(row["status"]),
            provider_created_at=row["provider_created_at"],
            tenant_id=None if row["tenant_id"] is None else str(row["tenant_id"]),
            workspace_id=None if row["workspace_id"] is None else str(row["workspace_id"]),
            trace_id=str(row["trace_id"]),
            degraded=bool(row["degraded"]),
        )

    async def mark_status(
        self,
        event_id: str,
        status: str,
        *,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        await self.conn.execute(
            """
            UPDATE support.support_events
               SET status = %s,
                   tenant_id = COALESCE(%s, tenant_id),
                   workspace_id = COALESCE(%s, workspace_id),
                   updated_at = now()
             WHERE id = %s
            """,
            [status, tenant_id, workspace_id, event_id],
        )


class OutboxRepository(Repository):
    async def enqueue(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime,
        trace_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        retry_of: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        event_id = str(uuid4())
        await self.conn.execute(
            """
            INSERT INTO integration.outbox_events
              (id, event_type, tenant_id, workspace_id, trace_id, occurred_at,
               retry_of, payload, available_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
            """,
            [
                event_id,
                event_type,
                tenant_id,
                workspace_id,
                trace_id,
                occurred_at,
                retry_of,
                Jsonb(payload),
                available_at,
            ],
        )
        return event_id

    async def claim_one(self, worker_id: str) -> OutboxEvent | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE integration.outbox_events
                   SET status = 'processing',
                       locked_at = now(),
                       locked_by = %s,
                       attempt = attempt + 1,
                       updated_at = now()
                 WHERE id = (
                   SELECT id FROM integration.outbox_events
                    WHERE status = 'pending' AND available_at <= now()
                    ORDER BY available_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                 )
                RETURNING id, event_type, schema_version, tenant_id, workspace_id,
                          trace_id, attempt, retry_of, payload
                """,
                [worker_id],
            )
            row = await cur.fetchone()
        return None if row is None else _outbox_event(row)

    async def mark_completed(self, event_id: str) -> None:
        await self.conn.execute(
            """
            UPDATE integration.outbox_events
               SET status = 'completed', locked_at = NULL, locked_by = NULL,
                   updated_at = now()
             WHERE id = %s
            """,
            [event_id],
        )

    async def mark_retry(self, event_id: str, *, available_at: datetime, error: str) -> None:
        await self.conn.execute(
            """
            UPDATE integration.outbox_events
               SET status = 'pending', locked_at = NULL, locked_by = NULL,
                   available_at = %s, last_error = %s, updated_at = now()
             WHERE id = %s
            """,
            [available_at, error, event_id],
        )

    async def mark_dead_letter(self, event_id: str, *, error: str) -> None:
        await self.conn.execute(
            """
            UPDATE integration.outbox_events
               SET status = 'dead_letter', locked_at = NULL, locked_by = NULL,
                   last_error = %s, updated_at = now()
             WHERE id = %s
            """,
            [error, event_id],
        )

    async def reclaim_stale(self, *, older_than_seconds: int) -> int:
        """回收崩溃 Worker 遗留的 processing 事件，使其重新可被领取。"""
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE integration.outbox_events
                   SET status = 'pending', locked_at = NULL, locked_by = NULL,
                       updated_at = now()
                 WHERE status = 'processing'
                   AND locked_at < now() - make_interval(secs => %s)
                """,
                [older_than_seconds],
            )
            return cur.rowcount


class ConversationsRepository(Repository):
    async def ensure(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        external_id: str,
        channel_id: str | None = None,
        provider_created_at: datetime | None = None,
    ) -> str:
        conversation_id = str(uuid4())
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO support.conversations
                  (id, tenant_id, workspace_id, channel_id, external_id, provider_created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, external_id) DO NOTHING
                """,
                [
                    conversation_id,
                    tenant_id,
                    workspace_id,
                    channel_id,
                    external_id,
                    provider_created_at,
                ],
            )
            if cur.rowcount == 1:
                return conversation_id
            await cur.execute(
                """
                SELECT id FROM support.conversations
                 WHERE workspace_id = %s AND external_id = %s
                """,
                [workspace_id, external_id],
            )
            row = await cur.fetchone()
        if row is None:
            raise RuntimeError("conversation conflict without existing row")
        return str(row[0])


class MessagesRepository(Repository):
    async def ensure(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        conversation_id: str,
        external_id: str,
        direction: str,
        provider_created_at: datetime | None,
        content_ref: str | None,
    ) -> str:
        message_id = str(uuid4())
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO support.messages
                  (id, tenant_id, workspace_id, conversation_id, external_id,
                   direction, provider_created_at, content_ref)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (conversation_id, external_id) DO NOTHING
                """,
                [
                    message_id,
                    tenant_id,
                    workspace_id,
                    conversation_id,
                    external_id,
                    direction,
                    provider_created_at,
                    content_ref,
                ],
            )
            if cur.rowcount == 1:
                return message_id
            await cur.execute(
                """
                SELECT id FROM support.messages
                 WHERE conversation_id = %s AND external_id = %s
                """,
                [conversation_id, external_id],
            )
            row = await cur.fetchone()
        if row is None:
            raise RuntimeError("message conflict without existing row")
        return str(row[0])


class MessageProcessingRepository(Repository):
    async def claim(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        message_id: str,
        processing_type: str,
    ) -> str | None:
        """返回新记录 ID；None 表示同一 (message, processing_type) 已被领取过。"""
        record_id = str(uuid4())
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO integration.message_processing_records
                  (id, tenant_id, workspace_id, message_id, processing_type, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                ON CONFLICT (message_id, processing_type) DO NOTHING
                """,
                [record_id, tenant_id, workspace_id, message_id, processing_type],
            )
            return record_id if cur.rowcount == 1 else None

    async def mark_completed(self, record_id: str) -> None:
        await self.conn.execute(
            """
            UPDATE integration.message_processing_records
               SET status = 'completed', updated_at = now()
             WHERE id = %s
            """,
            [record_id],
        )


def _outbox_event(row: dict[str, Any]) -> OutboxEvent:
    return OutboxEvent(
        id=str(row["id"]),
        event_type=str(row["event_type"]),
        schema_version=int(row["schema_version"]),
        tenant_id=None if row["tenant_id"] is None else str(row["tenant_id"]),
        workspace_id=None if row["workspace_id"] is None else str(row["workspace_id"]),
        trace_id=str(row["trace_id"]),
        attempt=int(row["attempt"]),
        retry_of=None if row["retry_of"] is None else str(row["retry_of"]),
        payload=dict(row["payload"]),
    )
