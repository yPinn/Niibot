"""Versioned cross-process contract for assistant scope changes."""

from __future__ import annotations

import json

import pytest

from shared.assistant import (
    ASSISTANT_SCOPE_CHANGED_CHANNEL,
    AssistantMode,
    AssistantScopeChange,
)


def test_roleplay_scope_round_trip_is_versioned_and_secret_free() -> None:
    change = AssistantScopeChange(
        channel_id="channel-a",
        assistant_mode=AssistantMode.ROLEPLAY,
        active_roleplay_revision_id=41,
    )

    payload = change.to_payload()

    assert ASSISTANT_SCOPE_CHANGED_CHANNEL == "assistant_scope_changed"
    assert json.loads(payload) == {
        "version": 1,
        "channel_id": "channel-a",
        "assistant_mode": "roleplay",
        "active_roleplay_revision_id": 41,
    }
    assert AssistantScopeChange.from_payload(payload) == change


def test_persona_scope_requires_a_null_revision() -> None:
    with pytest.raises(ValueError):
        AssistantScopeChange(
            channel_id="channel-a",
            assistant_mode=AssistantMode.PERSONA,
            active_roleplay_revision_id=41,
        )


def test_roleplay_scope_requires_a_positive_revision() -> None:
    for invalid in (None, 0, -1):
        with pytest.raises(ValueError):
            AssistantScopeChange(
                channel_id="channel-a",
                assistant_mode=AssistantMode.ROLEPLAY,
                active_roleplay_revision_id=invalid,
            )


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"version":2,"channel_id":"channel-a","assistant_mode":"persona",'
        '"active_roleplay_revision_id":null}',
        '{"version":1,"channel_id":"channel-a","assistant_mode":"persona",'
        '"active_roleplay_revision_id":null,"token":"secret"}',
        '{"version":1,"channel_id":7,"assistant_mode":"persona",'
        '"active_roleplay_revision_id":null}',
    ],
)
def test_decode_rejects_malformed_unknown_or_wrong_version_payload(payload: str) -> None:
    with pytest.raises(ValueError):
        AssistantScopeChange.from_payload(payload)
