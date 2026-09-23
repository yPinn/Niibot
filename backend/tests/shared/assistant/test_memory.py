"""Contracts for bounded, process-local assistant conversation memory."""

from __future__ import annotations

from dataclasses import asdict

from shared.assistant.memory import (
    BoundedConversationMemoryStore,
    ConversationKey,
    ConversationTurn,
    NullConversationMemoryStore,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _key(
    viewer: str,
    *,
    channel: str = "channel-1",
    assistant_scope: str = "persona",
) -> ConversationKey:
    return ConversationKey("twitch", channel, viewer, assistant_scope)


def _turn(user: str = "hi", assistant: str = "hello") -> ConversationTurn:
    return ConversationTurn(user, assistant)


def _store(clock: _Clock, **overrides: int) -> BoundedConversationMemoryStore:
    limits = {
        "ttl_seconds": 600,
        "max_sessions": 500,
        "max_turns_per_session": 2,
        "max_chars_per_session": 1_000,
        "max_total_chars": 500_000,
    }
    limits.update(overrides)
    return BoundedConversationMemoryStore(clock=clock, **limits)


def test_null_store_never_retains_content() -> None:
    store = NullConversationMemoryStore()
    key = _key("viewer-1")

    assert store.append(key, _turn()) is False
    assert store.get(key) == ()
    assert store.clear_channel("twitch", "channel-1") == 0
    assert store.clear_channel_except_scope("twitch", "channel-1", "persona") == 0
    assert store.stats().active_sessions == 0


def test_sessions_are_isolated_by_platform_channel_participant_and_assistant_scope() -> None:
    clock = _Clock()
    store = _store(clock)
    first = _key("viewer-1")
    second = _key("viewer-2")
    other_channel = _key("viewer-1", channel="channel-2")
    other_platform = ConversationKey("discord", "channel-1", "viewer-1", "persona")
    other_scope = _key("viewer-1", assistant_scope="roleplay:41")

    store.append(first, _turn("one", "answer-one"))

    assert store.get(first) == (_turn("one", "answer-one"),)
    assert store.get(second) == ()
    assert store.get(other_channel) == ()
    assert store.get(other_platform) == ()
    assert store.get(other_scope) == ()


def test_scope_switch_keeps_old_history_inaccessible_without_sender_identity() -> None:
    clock = _Clock()
    store = _store(clock)
    persona = _key("viewer-1", assistant_scope="persona")
    roleplay = _key("viewer-1", assistant_scope="roleplay:41")

    store.append(persona, _turn("persona question", "persona answer"))
    store.append(roleplay, _turn("role question", "role answer"))

    assert store.get(persona) == (_turn("persona question", "persona answer"),)
    assert store.get(roleplay) == (_turn("role question", "role answer"),)
    assert store.stats().active_sessions == 2


def test_ttl_expires_from_last_successful_append_not_read() -> None:
    clock = _Clock()
    store = _store(clock, ttl_seconds=10)
    key = _key("viewer-1")
    store.append(key, _turn())

    clock.advance(9)
    assert store.get(key) == (_turn(),)
    clock.advance(2)

    assert store.get(key) == ()
    assert store.stats().ttl_evictions == 1


def test_only_most_recent_turns_are_retained() -> None:
    clock = _Clock()
    store = _store(clock, max_turns_per_session=2)
    key = _key("viewer-1")

    store.append(key, _turn("one", "a"))
    store.append(key, _turn("two", "b"))
    store.append(key, _turn("three", "c"))

    assert store.get(key) == (_turn("two", "b"), _turn("three", "c"))


def test_oversized_turn_is_rejected_without_replacing_existing_history() -> None:
    clock = _Clock()
    store = _store(clock, max_chars_per_session=10)
    key = _key("viewer-1")
    store.append(key, _turn("hi", "ok"))

    assert store.append(key, _turn("123456", "12345")) is False
    assert store.get(key) == (_turn("hi", "ok"),)
    assert store.stats().oversized_turn_rejections == 1


def test_session_budget_drops_oldest_turns() -> None:
    clock = _Clock()
    store = _store(clock, max_turns_per_session=3, max_chars_per_session=10)
    key = _key("viewer-1")

    store.append(key, _turn("111", "aa"))
    store.append(key, _turn("222", "bb"))
    store.append(key, _turn("333", "cc"))

    assert store.get(key) == (_turn("222", "bb"), _turn("333", "cc"))


def test_lru_session_cap_evicts_least_recently_accessed_session() -> None:
    clock = _Clock()
    store = _store(clock, max_sessions=2)
    first, second, third = _key("one"), _key("two"), _key("three")
    store.append(first, _turn())
    store.append(second, _turn())
    store.get(first)

    store.append(third, _turn())

    assert store.get(first)
    assert store.get(second) == ()
    assert store.get(third)
    assert store.stats().lru_evictions == 1


def test_global_character_budget_evicts_whole_lru_sessions() -> None:
    clock = _Clock()
    store = _store(
        clock,
        max_sessions=10,
        max_chars_per_session=10,
        max_total_chars=12,
    )
    first, second, third = _key("one"), _key("two"), _key("three")
    store.append(first, _turn("111", "aaa"))
    store.append(second, _turn("222", "bbb"))

    store.append(third, _turn("33", "bb"))

    assert store.get(first) == ()
    assert store.get(second)
    assert store.get(third)
    assert store.stats().budget_evictions == 1
    assert store.stats().total_chars == 10


def test_clear_channel_removes_only_matching_platform_channel() -> None:
    clock = _Clock()
    store = _store(clock)
    store.append(_key("one"), _turn())
    store.append(_key("two"), _turn())
    store.append(_key("three", channel="channel-2"), _turn())

    assert store.clear_channel("twitch", "channel-1") == 2
    assert store.get(_key("one")) == ()
    assert store.get(_key("three", channel="channel-2"))


def test_scope_change_removes_old_scopes_but_preserves_current_scope() -> None:
    clock = _Clock()
    store = _store(clock)
    current = _key("one", assistant_scope="roleplay:41")
    old_persona = _key("two", assistant_scope="persona")
    old_revision = _key("three", assistant_scope="roleplay:40")
    other_channel = _key(
        "four",
        channel="channel-2",
        assistant_scope="persona",
    )
    for key in (current, old_persona, old_revision, other_channel):
        store.append(key, _turn())

    removed = store.clear_channel_except_scope(
        "twitch",
        "channel-1",
        "roleplay:41",
    )

    assert removed == 2
    assert store.get(current)
    assert store.get(old_persona) == ()
    assert store.get(old_revision) == ()
    assert store.get(other_channel)


def test_stats_are_aggregate_only_and_do_not_expose_keys_or_content() -> None:
    clock = _Clock()
    store = _store(clock)
    store.append(_key("secret-viewer-id"), _turn("private question", "private answer"))

    payload = asdict(store.stats())
    rendered = repr(payload)

    assert payload["active_sessions"] == 1
    assert payload["total_chars"] == len("private questionprivate answer")
    assert "secret-viewer-id" not in rendered
    assert "private question" not in rendered
    assert "private answer" not in rendered
