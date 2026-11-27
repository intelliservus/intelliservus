from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

# 上游只有这三类事件带「创建」语义，缺失 Delivery ID 时可用复合键兜底（ADR-003）。
CREATE_EVENT_TYPES = frozenset(
    {"message_created", "conversation_created", "contact_created"}
)


def project_event(payload: dict[str, Any]) -> dict[str, Any]:
    """把上游 payload 投影为顶层字段白名单，丢弃会话历史等嵌套结构。"""
    account = payload.get("account") or {}
    inbox = payload.get("inbox") or {}
    conversation = payload.get("conversation") or {}
    sender = payload.get("sender") or {}
    event_type = str(payload.get("event") or "")

    conversation_id = conversation.get("id")
    if conversation_id is None and event_type.startswith("conversation_"):
        conversation_id = payload.get("id")

    return {
        "event": event_type,
        "id": payload.get("id"),
        "account_id": account.get("id"),
        "inbox_id": inbox.get("id") if inbox else payload.get("inbox_id"),
        "conversation_id": conversation_id,
        "sender_type": sender.get("type"),
        "sender_id": sender.get("id"),
        "message_type": payload.get("message_type"),
        "private": bool(payload.get("private", False)),
        "content_type": payload.get("content_type"),
        "source_id": payload.get("source_id"),
        "status": payload.get("status"),
        "created_at": payload.get("created_at"),
        "content": payload.get("content"),
    }


def provider_created_at(payload: dict[str, Any]) -> datetime | None:
    """上游时间戳：消息是 ISO 字符串，会话事件是 Unix 秒，联系人事件没有。"""
    value = payload.get("created_at")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def delivery_key(headers: Any, payload: dict[str, Any]) -> tuple[str, bool]:
    """返回 (delivery_key, degraded)。

    优先使用 `X-Chatwoot-Delivery`；缺失时创建型事件用 §5.4 复合键，
    更新型事件无法安全去重，改用随机键交由业务层幂等吸收（ADR-003）。
    """
    delivery = headers.get("x-chatwoot-delivery")
    if delivery:
        return str(delivery), False

    event_type = str(payload.get("event") or "")
    if event_type in CREATE_EVENT_TYPES:
        conversation = payload.get("conversation") or {}
        parts = [
            event_type,
            str(payload.get("id")),
            str(conversation.get("id")),
            str(payload.get("created_at")),
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return f"degraded:{digest}", True

    return f"degraded:{uuid4()}", True
