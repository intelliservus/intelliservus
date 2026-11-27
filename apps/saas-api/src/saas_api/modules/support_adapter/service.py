from __future__ import annotations

import hashlib
from typing import Any, Literal

from psycopg_pool import AsyncConnectionPool

from ...common.logging import JsonLogger
from ...database.transaction import tenant_context
from .adapter import MESSAGE_EVENTS, should_filter, to_standard_event
from .mapping import MappingResolver, Unresolved
from .repositories import (
    ConversationsRepository,
    MessageProcessingRepository,
    MessagesRepository,
    OutboxEvent,
    SupportEventsRepository,
)

ProcessingOutcome = Literal["filtered", "pending_mapping", "published", "skipped_duplicate"]

PROCESSING_TYPE_AGENT_RUN = "agent_run"


class ProcessingError(Exception):
    """消费失败。`permanent` 决定进重试还是直接死信（事实源 §5.7）。"""

    def __init__(self, message: str, *, permanent: bool) -> None:
        super().__init__(message)
        self.permanent = permanent


class SupportAdapterService:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        resolver: MappingResolver,
        logger: JsonLogger,
    ) -> None:
        self._pool = pool
        self._resolver = resolver
        self._logger = logger

    async def process(self, event: OutboxEvent) -> ProcessingOutcome:
        support_event_id = event.payload.get("support_event_id")
        if not support_event_id:
            raise ProcessingError("missing support_event_id", permanent=True)

        async with tenant_context(self._pool, None) as conn:
            record = await SupportEventsRepository(conn).find(str(support_event_id))
        if record is None:
            raise ProcessingError("support event not found", permanent=True)

        normalized = to_standard_event(record.payload, record.provider_created_at)
        decision = should_filter(normalized)
        if decision.dropped:
            async with tenant_context(self._pool, None) as conn:
                await SupportEventsRepository(conn).mark_status(record.id, "filtered")
            self._logger.info(
                "MESSAGE_FILTERED",
                "event dropped by filter chain",
                None,
                support_event_id=record.id,
                reason=decision.reason,
            )
            return "filtered"

        async with tenant_context(self._pool, None) as conn:
            mapping = await self._resolver.resolve(
                conn,
                provider="chatwoot",
                account_id=normalized.account_id,
                inbox_id=normalized.inbox_id,
            )
        if isinstance(mapping, Unresolved):
            async with tenant_context(self._pool, None) as conn:
                await SupportEventsRepository(conn).mark_status(record.id, "pending_mapping")
            self._logger.info(
                "SUPPORT_EVENT_PENDING_MAPPING",
                "event parked until channel mapping exists",
                None,
                support_event_id=record.id,
                reason=mapping.reason,
            )
            return "pending_mapping"

        external_message_id = normalized.external_message_id
        external_conversation_id = normalized.external_conversation_id
        if (
            normalized.raw_event_type not in MESSAGE_EVENTS
            or external_message_id is None
            or external_conversation_id is None
        ):
            async with tenant_context(self._pool, mapping.tenant_id) as conn:
                await SupportEventsRepository(conn).mark_status(
                    record.id,
                    "published",
                    tenant_id=mapping.tenant_id,
                    workspace_id=mapping.workspace_id,
                )
            return "published"

        async with tenant_context(self._pool, mapping.tenant_id) as conn:
            conversation_id = await ConversationsRepository(conn).ensure(
                tenant_id=mapping.tenant_id,
                workspace_id=mapping.workspace_id,
                external_id=external_conversation_id,
                channel_id=mapping.channel_id,
                provider_created_at=normalized.provider_created_at,
            )
            message_id = await MessagesRepository(conn).ensure(
                tenant_id=mapping.tenant_id,
                workspace_id=mapping.workspace_id,
                conversation_id=conversation_id,
                external_id=external_message_id,
                direction="inbound",
                provider_created_at=normalized.provider_created_at,
                content_ref=_content_ref(normalized.content),
            )
            record_id = await MessageProcessingRepository(conn).claim(
                tenant_id=mapping.tenant_id,
                workspace_id=mapping.workspace_id,
                message_id=message_id,
                processing_type=PROCESSING_TYPE_AGENT_RUN,
            )
            await SupportEventsRepository(conn).mark_status(
                record.id,
                "published",
                tenant_id=mapping.tenant_id,
                workspace_id=mapping.workspace_id,
            )

        if record_id is None:
            self._logger.info(
                "MESSAGE_SKIPPED_DUPLICATE",
                "message already claimed by another processing record",
                None,
                support_event_id=record.id,
            )
            return "skipped_duplicate"

        self._logger.info(
            "MESSAGE_PUBLISHED",
            "message persisted for downstream coordination",
            None,
            support_event_id=record.id,
            processing_record_id=record_id,
        )
        return "published"


def _content_ref(content: Any) -> str | None:
    if content is None:
        return None
    return "sha256:" + hashlib.sha256(str(content).encode("utf-8")).hexdigest()[:32]
