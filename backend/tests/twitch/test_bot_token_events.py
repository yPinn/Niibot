"""Unit tests for Bot token-event handlers.

Covers:
- event_token_refreshed: persists refreshed tokens + scopes to DB
- event_subscription_revoked: flags reauth on authorization_revoked
- add_token: persists twitchio's current token, not stale call args
- load_tokens: reauth-notification cooldown
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

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


# ---------------------------------------------------------------------------
# add_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddToken:
    async def test_persists_current_token_not_stale_args(self, bot):
        """super().add_token() may refresh internally when the passed-in token is
        near expiry, firing a fire-and-forget token_refreshed event with the NEW
        pair. The override must persist whatever twitchio is now holding — not
        the stale pre-refresh args it was called with — or a race with
        event_token_refreshed()'s persist can clobber a fresh refresh_token with
        one Twitch has already rotated away."""
        resp = MagicMock(user_id="u1", scopes=["channel:bot"])
        with (
            patch("twitchio.client.Client.add_token", new=AsyncMock(return_value=resp)),
            patch(
                "twitchio.client.Client.tokens",
                new_callable=PropertyMock,
                return_value={"u1": {"token": "fresh_tok", "refresh": "fresh_ref"}},
            ),
        ):
            await bot.add_token("stale_tok", "stale_ref")

        bot.channels.upsert_token_only.assert_awaited_once_with(
            "u1", "fresh_tok", "fresh_ref", scopes="channel:bot", token_type="broadcaster"
        )

    async def test_falls_back_to_call_args_when_user_not_in_tokens_map(self, bot):
        resp = MagicMock(user_id="u1", scopes=[])
        with (
            patch("twitchio.client.Client.add_token", new=AsyncMock(return_value=resp)),
            patch("twitchio.client.Client.tokens", new_callable=PropertyMock, return_value={}),
        ):
            await bot.add_token("tok", "ref")

        bot.channels.upsert_token_only.assert_awaited_once_with(
            "u1", "tok", "ref", scopes=None, token_type="broadcaster"
        )


# ---------------------------------------------------------------------------
# load_tokens — reauth notification cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoadTokens:
    @pytest.fixture()
    def load_bot(self, bot):
        bot.channels.list_tokens = AsyncMock()
        bot.add_channel_to_db = AsyncMock()
        bot._mark_reauth_required = AsyncMock()
        return bot

    @staticmethod
    def _token(reauth_notified_at):
        from shared.models.channel import Token

        return Token(
            user_id="u1",
            token="tok",
            refresh="ref",
            token_type="broadcaster",
            reauth_notified_at=reauth_notified_at,
        )

    async def test_never_notified_logs_and_marks(self, load_bot, caplog):
        load_bot.channels.list_tokens.return_value = [self._token(None)]
        user_info = MagicMock(user_id="u1", login="streamer", scopes=["channel:bot"])
        load_bot.add_token = AsyncMock(return_value=user_info)

        with caplog.at_level(logging.WARNING):
            await load_bot.load_tokens()

        load_bot._mark_reauth_required.assert_awaited_once_with("u1")
        assert "u1" in load_bot._needs_reauth
        assert any("missing scopes" in r.message for r in caplog.records)

    async def test_within_cooldown_skips_notify_but_keeps_flag(self, load_bot):
        recent = datetime.now(UTC) - timedelta(hours=1)
        load_bot.channels.list_tokens.return_value = [self._token(recent)]
        user_info = MagicMock(user_id="u1", login="streamer", scopes=["channel:bot"])
        load_bot.add_token = AsyncMock(return_value=user_info)

        await load_bot.load_tokens()

        load_bot._mark_reauth_required.assert_not_awaited()
        assert "u1" in load_bot._needs_reauth

    async def test_past_cooldown_notifies_again(self, load_bot):
        stale = datetime.now(UTC) - timedelta(hours=13)
        load_bot.channels.list_tokens.return_value = [self._token(stale)]
        user_info = MagicMock(user_id="u1", login="streamer", scopes=["channel:bot"])
        load_bot.add_token = AsyncMock(return_value=user_info)

        await load_bot.load_tokens()

        load_bot._mark_reauth_required.assert_awaited_once_with("u1")


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

    async def test_authorization_revoked_clears_subscription_state(self, revoked_bot):
        # Without this, is_subscribed() keeps returning True for a token Twitch
        # already killed, so a later reauth's subscribe() call becomes a no-op
        # and the channel never gets its EventSub subscriptions back.
        revoked_bot.subs._subscribed = {"ch1"}
        revoked_bot.subs._sub_ids = {"ch1": ["sub-a"]}

        await revoked_bot.event_subscription_revoked(_make_revoked_payload("authorization_revoked"))

        assert not revoked_bot.subs.is_subscribed("ch1")
        assert "ch1" not in revoked_bot.subs._sub_ids

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
