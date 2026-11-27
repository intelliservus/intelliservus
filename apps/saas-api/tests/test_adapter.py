from __future__ import annotations

from typing import Any

import pytest

from saas_api.modules.support_adapter.adapter import (
    should_filter,
    to_standard_event,
)
from saas_api.modules.support_adapter.events import project_event

BASE: dict[str, Any] = {
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


def test_projection_drops_conversation_history() -> None:
    small = project_event(BASE)
    history = [{"id": index, "content": "x" * 200} for index in range(500)]
    large = project_event({**BASE, "conversation": {"id": 5, "messages": history}})

    assert small == large
    assert "conversation" not in small


def test_projection_flattens_nested_ids() -> None:
    projected = project_event(BASE)

    assert projected["account_id"] == 1
    assert projected["inbox_id"] == 1
    assert projected["conversation_id"] == 5
    assert projected["sender_type"] == "contact"
    assert projected["private"] is False


def test_projection_reads_conversation_event_fields() -> None:
    projected = project_event(
        {
            "event": "conversation_created",
            "id": 5,
            "created_at": 1795609471,
            "inbox_id": 1,
            "account": {"id": 1},
            "messages": [{"id": 1}],
        }
    )

    assert projected["conversation_id"] == 5
    assert projected["inbox_id"] == 1
    assert "messages" not in projected


@pytest.mark.parametrize(
    ("raw_event_type", "message_type", "expected"),
    [
        ("message_created", "incoming", "conversation.message.received"),
        ("message_created", "outgoing", "conversation.message.outbound"),
        ("message_updated", "incoming", "conversation.message.updated"),
        ("conversation_created", None, "conversation.created"),
        ("conversation_updated", None, "conversation.updated"),
        ("conversation_status_changed", None, "conversation.updated"),
        ("contact_created", None, "contact.created"),
        ("contact_updated", None, "contact.updated"),
        ("something_new", None, "chatwoot.something_new"),
    ],
)
def test_standard_event_type_mapping(
    raw_event_type: str, message_type: str | None, expected: str
) -> None:
    payload = {**project_event(BASE), "event": raw_event_type, "message_type": message_type}

    assert to_standard_event(payload, provider_time=None).event_type == expected


@pytest.mark.parametrize(
    ("overrides", "dropped", "reason"),
    [
        ({}, False, None),
        ({"sender_type": "agent_bot"}, True, "sender_agent_bot"),
        ({"sender_type": "user", "message_type": "outgoing"}, True, "sender_user"),
        ({"sender_type": "system"}, True, "sender_system"),
        ({"private": True}, True, "private_note"),
        ({"message_type": "outgoing"}, True, "message_type_outgoing"),
        ({"message_type": "activity"}, True, "message_type_activity"),
        ({"message_type": "template"}, True, "message_type_template"),
    ],
)
def test_filter_matrix(
    overrides: dict[str, Any], dropped: bool, reason: str | None
) -> None:
    payload = {**project_event(BASE), **overrides}
    event = to_standard_event(payload, provider_time=None)

    decision = should_filter(event)

    assert decision.dropped is dropped
    assert decision.reason == reason


def test_metadata_events_are_not_filtered() -> None:
    payload = {**project_event(BASE), "event": "conversation_created"}

    assert should_filter(to_standard_event(payload, provider_time=None)).dropped is False
