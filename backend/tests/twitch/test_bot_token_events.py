"""Unit tests for Bot token-event handlers.

Covers:
- event_token_refreshed: persists refreshed tokens + scopes to DB
- event_subscription_revoked: flags reauth on authorization_revoked
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token_refreshed_payload(
    user_id: str,
    token: str,
    refresh_token: str,
    scopes: list[str] | None = None,
) -> MagicMock:
    payload = MagicMock()
    payload.user_id = user_id
    payload.token = token
    payload.refresh_token = refresh_token
    payload.scopes = scopes if scopes is not None else []
    return payload


def _make_revoked_payload(
    reason: str, *, condition: dict | None = None, sub_type: str = "channel.follow"
) -> MagicMock:
    payload = MagicMock()
    payload.raw = {
        "condition": condition if condition is not None else {"broadcaster_user_id": "ch1"}
    }
    payload.status = MagicMock(value=reason)
    payload.type = sub_type
    return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bot():
    """Bot instance with heavy deps mocked — minimal surface for token tests."""
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot
        from twitch.core.subscription_manager import SubscriptionManager

        b = Bot.__new__(Bot)
        b.channels = MagicMock()
        b.channels.upsert_token_only = AsyncMock()
        b.channels.get_token = AsyncMock()
        b._background_tasks = set()
        b._bot_id = "bot-001"
        b._client_id = "test-client-id"
        b._needs_reauth = set()
        b.subs = SubscriptionManager(
            bot_id="bot-001",
            multi_subscribe=AsyncMock(),
            delete_subscription=AsyncMock(),
            needs_reauth=b._needs_reauth,
        )
        b._bot_is_mod = set()
        b._mod_check_pending = set()
        b._token_refresh_buffer = []
        b._token_refresh_flush_task = None
        return b


# ---------------------------------------------------------------------------
# event_token_refreshed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEventTokenRefreshed:
    async def test_persists_token_and_scopes(self, bot):
        payload = _make_token_refreshed_payload(
            user_id="u1",
            token="new_tok",
            refresh_token="new_ref",
            scopes=["channel:bot", "channel:read:redemptions"],
        )

        await bot.event_token_refreshed(payload)

        bot.channels.upsert_token_only.assert_awaited_once_with(
            "u1",
            "new_tok",
            "new_ref",
            scopes="channel:bot channel:read:redemptions",
            token_type="broadcaster",
        )

    async def test_skips_when_no_user_id(self, bot):
        payload = _make_token_refreshed_payload(user_id="", token="tok", refresh_token="ref")

        await bot.event_token_refreshed(payload)

        bot.channels.upsert_token_only.assert_not_awaited()

    async def test_persists_with_none_scopes_when_scopes_empty(self, bot):
        payload = _make_token_refreshed_payload(
            user_id="u1", token="tok", refresh_token="ref", scopes=[]
        )

        await bot.event_token_refreshed(payload)

        bot.channels.upsert_token_only.assert_awaited_once_with(
            "u1", "tok", "ref", scopes=None, token_type="broadcaster"
        )

    async def test_persists_multiple_scopes_space_separated(self, bot):
        payload = _make_token_refreshed_payload(
            user_id="u1",
            token="tok",
            refresh_token="ref",
            scopes=["user:bot", "user:read:chat", "user:write:chat"],
        )

        await bot.event_token_refreshed(payload)

        _, kwargs = bot.channels.upsert_token_only.call_args
        assert kwargs["scopes"] == "user:bot user:read:chat user:write:chat"


@pytest.mark.asyncio
class TestEventSubscriptionRevoked:
    @pytest.fixture()
    def revoked_bot(self, bot):
        bot._ch = lambda cid: cid
        bot._mark_reauth_required = AsyncMock()
        return bot

    async def test_authorization_revoked_flags_reauth(self, revoked_bot):
        await revoked_bot.event_subscription_revoked(_make_revoked_payload("authorization_revoked"))
        revoked_bot._mark_reauth_required.assert_awaited_once_with("ch1")

    async def test_raid_condition_key_resolves_channel(self, revoked_bot):
        payload = _make_revoked_payload(
            "authorization_revoked", condition={"to_broadcaster_user_id": "ch2"}
        )
        await revoked_bot.event_subscription_revoked(payload)
        revoked_bot._mark_reauth_required.assert_awaited_once_with("ch2")

    async def test_non_auth_reason_does_not_flag_reauth(self, revoked_bot):
        await revoked_bot.event_subscription_revoked(
            _make_revoked_payload("notification_failures_exceeded")
        )
        revoked_bot._mark_reauth_required.assert_not_awaited()

    async def test_bot_own_id_does_not_flag_reauth(self, revoked_bot):
        payload = _make_revoked_payload(
            "authorization_revoked", condition={"broadcaster_user_id": "bot-001"}
        )
        await revoked_bot.event_subscription_revoked(payload)
        revoked_bot._mark_reauth_required.assert_not_awaited()
