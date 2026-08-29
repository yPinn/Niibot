"""Unit tests for Bot token-event handlers and watch-time token flow.

Covers:
- event_token_refreshed: persists refreshed tokens + scopes to DB
- _watch_time_loop: uses channels.get_token (repository layer), not raw SQL
"""

from __future__ import annotations

import asyncio
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
        patch("twitch.core.bot._ChannelMixin.__init__", return_value=None),
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot._SessionMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b.channels = MagicMock()
        b.channels.upsert_token_only = AsyncMock()
        b.channels.get_token = AsyncMock()
        b.analytics = MagicMock()
        b.analytics.increment_watch_seconds = AsyncMock()
        b._active_sessions = {}
        b._chatter_buffers = {}
        b._channel_line_counts = {}
        b._background_tasks = set()
        b._bot_id = "bot-001"
        b._client_id = "test-client-id"
        b._channel_names = {}
        b._bot_is_mod = set()
        b._mod_check_pending = set()
        b._needs_reauth = set()
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


# ---------------------------------------------------------------------------
# _watch_time_loop — delegates to _fetch_chatters (which uses the bot token)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWatchTimeLoopTokenFetch:
    async def _run_one_iteration(self, bot):
        """Run the watch-time loop for exactly one iteration then stop.

        The loop's end-of-iteration sleep is outside the inner try/except, so
        CancelledError propagates out of _watch_time_loop on the second sleep call.
        """
        sleep_calls = 0

        async def _one_shot(t):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", new=_one_shot):
            with pytest.raises(asyncio.CancelledError):
                await bot._watch_time_loop()

    async def test_calls_fetch_chatters_with_channel_id_only(self, bot):
        bot._active_sessions = {"ch1": 1}
        bot._fetch_chatters = AsyncMock(return_value=[])

        await self._run_one_iteration(bot)

        bot._fetch_chatters.assert_called_once_with("ch1")

    async def test_no_raw_sql_token_access(self, bot):
        """token_database must not be used — all token access goes through the repository."""
        bot._active_sessions = {"ch1": 1}
        bot._fetch_chatters = AsyncMock(return_value=[])
        bot.token_database = MagicMock()  # would fail loudly if called
        bot.token_database.fetchrow = AsyncMock(side_effect=AssertionError("raw SQL used!"))

        await self._run_one_iteration(bot)

        bot.token_database.fetchrow.assert_not_called()


# ---------------------------------------------------------------------------
# _fetch_chatters — reads chatters with the BOT token, moderator_id = bot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchChattersUsesBotToken:
    def _http_ctx(self, resp):
        ctx = MagicMock()
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, client

    async def test_uses_bot_token_and_bot_moderator_id(self, bot):
        from shared.models.channel import Token

        bot.channels.get_token = AsyncMock(
            return_value=Token(user_id="bot-001", token="BOT_TOK", refresh="ref")
        )
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": [], "pagination": {}}
        ctx, client = self._http_ctx(resp)

        with patch("twitch.core._session_mixin.httpx.AsyncClient", return_value=ctx):
            await bot._fetch_chatters("ch1")

        bot.channels.get_token.assert_awaited_once_with("bot-001", "bot")
        _, kwargs = client.get.call_args
        assert kwargs["params"]["moderator_id"] == "bot-001"
        assert kwargs["params"]["broadcaster_id"] == "ch1"
        assert kwargs["headers"]["Authorization"] == "Bearer BOT_TOK"

    async def test_returns_empty_when_no_bot_token(self, bot):
        bot.channels.get_token = AsyncMock(return_value=None)

        with patch("twitch.core._session_mixin.httpx.AsyncClient") as mock_client:
            result = await bot._fetch_chatters("ch1")

        assert result == []
        mock_client.assert_not_called()
