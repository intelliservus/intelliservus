from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn

from psycopg_pool import AsyncConnectionPool

from ...common.config import Settings
from ...common.errors import AppError
from ...common.logging import JsonLogger
from ...database.transaction import ingress_context
from ..support_adapter.events import delivery_key, project_event, provider_created_at
from ..support_adapter.repositories import (
    OutboxRepository,
    SupportEventsRepository,
    WebhookDeliveriesRepository,
)
from .signature import signature_is_valid

# 接收事务产出的 outbox 事件：只携带引用，避免在队列里复制消息内容。
SUPPORT_EVENT_RECEIVED = "support.event.received"


@dataclass(frozen=True)
class ReceiveResult:
    status: Literal["accepted", "duplicate"]
    event_type: str


class IngressService:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        settings: Settings,
        logger: JsonLogger,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._pool = pool
        self._settings = settings
        self._logger = logger
        self._clock = clock

    async def receive(
        self, *, raw: bytes, headers: Mapping[str, str], trace_id: str
    ) -> ReceiveResult:
        self._verify_timestamp(headers)
        self._verify_signature(headers, raw)

        payload = self._parse(raw)
        event_type = payload.get("event")
        account = payload.get("account")
        if not isinstance(event_type, str) or not event_type:
            raise AppError(400, "PARAM_INVALID", "missing event type")
        if not isinstance(account, dict) or account.get("id") is None:
            raise AppError(400, "PARAM_INVALID", "missing account id")

        key, degraded = delivery_key(headers, payload)
        projected = project_event(payload)

        async with ingress_context(self._pool) as conn:
            delivery_id = await WebhookDeliveriesRepository(conn).insert(
                provider="chatwoot",
                account_id=str(account["id"]),
                delivery_key=key,
                event_type=event_type,
                degraded=degraded,
            )
            if delivery_id is None:
                self._logger.info(
                    "WEBHOOK_DUPLICATE",
                    "duplicate delivery ignored",
                    None,
                    event_type=event_type,
                )
                return ReceiveResult("duplicate", event_type)

            event_id = await SupportEventsRepository(conn).insert(
                delivery_id=delivery_id,
                event_type=event_type,
                payload=projected,
                status="received",
                degraded=degraded,
                trace_id=trace_id,
                provider_created_at=provider_created_at(payload),
            )
            await OutboxRepository(conn).enqueue(
                event_type=SUPPORT_EVENT_RECEIVED,
                payload={"support_event_id": event_id, "delivery_id": delivery_id},
                occurred_at=datetime.now(UTC),
                trace_id=trace_id,
            )

        self._logger.info(
            "WEBHOOK_ACCEPTED",
            "webhook accepted",
            None,
            event_type=event_type,
            account_id=str(account["id"]),
            degraded=degraded,
        )
        return ReceiveResult("accepted", event_type)

    def _verify_timestamp(self, headers: Mapping[str, str]) -> None:
        timestamp = headers.get("x-chatwoot-timestamp")
        if not timestamp:
            self._reject("WEBHOOK_TIMESTAMP_INVALID", "missing X-Chatwoot-Timestamp")
        try:
            sent_at = int(timestamp)
        except ValueError:
            self._reject("WEBHOOK_TIMESTAMP_INVALID", "X-Chatwoot-Timestamp is not an integer")
        if abs(self._clock() - sent_at) > self._settings.webhook_timestamp_tolerance_seconds:
            self._reject("WEBHOOK_TIMESTAMP_INVALID", "timestamp outside tolerance window")

    def _verify_signature(self, headers: Mapping[str, str], raw: bytes) -> None:
        provided = headers.get("x-chatwoot-signature")
        if not provided:
            self._reject("WEBHOOK_SIGNATURE_INVALID", "missing X-Chatwoot-Signature")
        timestamp = headers.get("x-chatwoot-timestamp", "")
        if not self._settings.webhook_secrets:
            self._reject("WEBHOOK_SIGNATURE_INVALID", "no webhook secret configured")
        if not signature_is_valid(
            self._settings.webhook_secrets,
            timestamp=timestamp,
            body=raw,
            provided=provided,
        ):
            self._reject("WEBHOOK_SIGNATURE_INVALID", "signature mismatch")

    def _parse(self, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AppError(400, "PARAM_INVALID", "body must be valid JSON") from None
        if not isinstance(payload, dict):
            raise AppError(400, "PARAM_INVALID", "body must be a JSON object")
        return payload

    def _reject(self, code: str, reason: str) -> NoReturn:
        self._logger.warn(code, reason)
        raise AppError(401, code, reason)
