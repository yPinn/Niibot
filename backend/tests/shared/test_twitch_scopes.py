"""Twitch OAuth scope contracts stay feature-scoped and deployment-safe."""

from shared.twitch_scopes import (
    BOT_CORE_SCOPES,
    BOT_SCOPES,
    BROADCASTER_CORE_SCOPES,
    BROADCASTER_SCOPES,
    TWITCH_CAPABILITIES,
    missing_capability_scopes,
    required_core_scopes,
)


def test_runtime_core_is_smaller_than_full_oauth_request() -> None:
    assert BOT_CORE_SCOPES == ["user:bot", "user:read:chat", "user:write:chat"]
    assert BROADCASTER_CORE_SCOPES == ["channel:bot"]
    assert set(BOT_CORE_SCOPES) < set(BOT_SCOPES)
    assert set(BROADCASTER_CORE_SCOPES) < set(BROADCASTER_SCOPES)


def test_optional_mod_sync_scope_is_not_forced_into_default_broadcaster_oauth() -> None:
    capability = TWITCH_CAPABILITIES["moderator_sync_realtime"]

    assert capability.credential == "broadcaster"
    assert capability.scopes == ("moderation:read",)
    assert capability.core is False
    assert "moderation:read" not in BROADCASTER_SCOPES


def test_missing_optional_scope_locks_only_its_capability() -> None:
    granted = set(BROADCASTER_SCOPES)

    assert missing_capability_scopes("broadcaster_chat", granted) == []
    assert missing_capability_scopes("vip_management", granted) == []
    assert missing_capability_scopes("moderator_sync_realtime", granted) == ["moderation:read"]


def test_required_core_scopes_are_role_specific() -> None:
    assert required_core_scopes("bot") == frozenset(BOT_CORE_SCOPES)
    assert required_core_scopes("broadcaster") == frozenset(BROADCASTER_CORE_SCOPES)
