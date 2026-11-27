from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

MESSAGE_EVENTS = frozenset({"message_created", "message_updated"})

# 上游 sender 类型里，只有 `contact` 代表客户本人；其余都不能触发回复（事实源 §5.8）。
NON_CUSTOMER_SENDERS = frozenset({"agent_bot", "agent", "user", "bot", "system"})

STANDARD_EVENT_TYPES = {
    "conversation_created": "conversation.created",
    "conversation_updated": "conversation.updated",
    "conversation_status_changed": "conversation.updated",
    "contact_created": "contact.created",
    "contact_updated": "contact.updated",
}


@dataclass(frozen=True)
class NormalizedEvent:
    raw_event_type: str
    event_type: str
    account_id: str
    inbox_id: str | None
    external_message_id: str | None
    external_conversation_id: str | None
    sender_type: str | None
    message_type: str | None
    private: bool
    provider_created_at: datetime | None
    content: str | None


@dataclass(frozen=True)
class FilterDecision:
    dropped: bool
    reason: str | None = None


def to_standard_event(
    payload: dict[str, Any], provider_time: datetime | None
) -> NormalizedEvent:
    raw_event_type = str(payload.get("event") or "")
    message_type = payload.get("message_type")
    inbox_id = payload.get("inbox_id")
    return NormalizedEvent(
        raw_event_type=raw_event_type,
        event_type=_standard_event_type(raw_event_type, message_type),
        account_id=str(payload.get("account_id") or ""),
        inbox_id=None if inbox_id is None else str(inbox_id),
        external_message_id=_optional_str(payload.get("id")),
        external_conversation_id=_optional_str(payload.get("conversation_id")),
        sender_type=_optional_str(payload.get("sender_type")),
        message_type=None if message_type is None else str(message_type),
        private=bool(payload.get("private", False)),
        provider_created_at=provider_time,
        content=_optional_str(payload.get("content")),
    )


def should_filter(event: NormalizedEvent) -> FilterDecision:
    if event.raw_event_type not in MESSAGE_EVENTS:
        return FilterDecision(False)
    if event.sender_type in NON_CUSTOMER_SENDERS:
        return FilterDecision(True, f"sender_{event.sender_type}")
    if event.private:
        return FilterDecision(True, "private_note")
    if event.message_type != "incoming":
        return FilterDecision(True, f"message_type_{event.message_type}")
    return FilterDecision(False)


def _standard_event_type(raw_event_type: str, message_type: Any) -> str:
    if raw_event_type in MESSAGE_EVENTS:
        if raw_event_type == "message_updated":
            return "conversation.message.updated"
        return (
            "conversation.message.received"
            if message_type == "incoming"
            else "conversation.message.outbound"
        )
    return STANDARD_EVENT_TYPES.get(raw_event_type, f"chatwoot.{raw_event_type}")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
