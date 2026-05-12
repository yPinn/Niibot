"""Tests for _NotifyMixin._handle_channel_toggle and Bot._check_bot_mod_status."""

from __future__ import annotations

import json
import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core._notify_mixin import _NotifyMixin

# ---------------------------------------------------------------------------
# Minimal concrete stub of _NotifyMixin
# ---------------------------------------------------------------------------


class _StubMixin(_NotifyMixin):
    """Provides the attributes that _NotifyMixin references via self.*."""

    def __init__(self) -> None:
        self._bot_id = "bot-001"
        self._subscribed_channels: set[str] = set()
        self._bot_is_mod: set[str] = set()
        self.subscribe_channel_events = AsyncMock()
        self.unsubscribe_channel_events = AsyncMock()
        self._check_bot_mod_status = AsyncMock()
        self._send_welcome_message = AsyncMock()
        self.redemption_configs = MagicMock()
        self.redemption_configs.ensure_defaults = AsyncMock()
        self.command_configs = MagicMock()
        self.command_configs.warm_cache = AsyncMock(return_value=0)
        self.owner_id = "owner-001"


def _payload(channel_id: str, *, enabled: bool) -> str:
    return json.dumps({"channel_id": channel_id, "enabled": enabled})


# ---------------------------------------------------------------------------
# _handle_channel_toggle — DISABLE
# ---------------------------------------------------------------------------


class TestHandleChannelToggleDisable:
    pytestmark = pytest.mark.asyncio

    async def test_disable_discards_bot_is_mod(self):
        mixin = _StubMixin()
        mixin._subscribed_channels = {"ch1"}
        mixin._bot_is_mod = {"ch1"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch1", enabled=False)
        )

        assert "ch1" not in mixin._bot_is_mod
        mixin.unsubscribe_channel_events.assert_awaited_once_with("ch1")

    async def test_disable_not_subscribed_skips_discard(self):
        """DISABLE for a channel that was already unsubscribed is a no-op."""
        mixin = _StubMixin()
        mixin._subscribed_channels = set()
        mixin._bot_is_mod = {"ch1"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch1", enabled=False)
        )

        mixin.unsubscribe_channel_events.assert_not_awaited()
        assert "ch1" in mixin._bot_is_mod  # discard not reached, set unchanged

    async def test_disable_ignores_bot_own_channel(self):
        mixin = _StubMixin()
        mixin._subscribed_channels = {"bot-001"}
        mixin._bot_is_mod = {"bot-001"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("bot-001", enabled=False)
        )

        mixin.unsubscribe_channel_events.assert_not_awaited()
        assert "bot-001" in mixin._bot_is_mod  # early-return, unchanged


# ---------------------------------------------------------------------------
# _handle_channel_toggle — ENABLE
# ---------------------------------------------------------------------------


class TestHandleChannelToggleEnable:
    pytestmark = pytest.mark.asyncio

    async def test_enable_calls_check_mod_status_after_subscribe(self):
        mixin = _StubMixin()

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch2", enabled=True)
        )

        mixin.subscribe_channel_events.assert_awaited_once_with("ch2")
        mixin._check_bot_mod_status.assert_awaited_once_with("ch2")

    async def test_enable_already_subscribed_skips_subscribe_and_mod_check(self):
        mixin = _StubMixin()
        mixin._subscribed_channels = {"ch2"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch2", enabled=True)
        )

        mixin.subscribe_channel_events.assert_not_awaited()
        mixin._check_bot_mod_status.assert_not_awaited()

    async def test_enable_ignores_bot_own_channel(self):
        mixin = _StubMixin()

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("bot-001", enabled=True)
        )

        mixin.subscribe_channel_events.assert_not_awaited()
        mixin._check_bot_mod_status.assert_not_awaited()


# ---------------------------------------------------------------------------
# Bot._check_bot_mod_status
# ---------------------------------------------------------------------------


def _make_httpx_ctx(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Build a mock for `async with httpx.AsyncClient(...) as client`."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    if json_data is not None:
        mock_resp.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.fixture()
def mod_bot():
    """Minimal Bot instance wired only for _check_bot_mod_status."""
    with (
        patch("twitch.core.bot._ChannelMixin.__init__", return_value=None),
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot._SessionMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._bot_id = "bot-001"
        b._client_id = "test-client-id"
        b._bot_is_mod = set()
        b._mod_check_pending = set()
        b.channels = MagicMock()
        return b


class TestCheckBotModStatus:
    pytestmark = pytest.mark.asyncio

    async def test_adds_to_bot_is_mod_when_api_confirms_mod(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)
        ctx = _make_httpx_ctx(200, {"data": [{"user_id": "bot-001"}]})

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")

        assert "ch1" in mod_bot._bot_is_mod

    async def test_does_not_add_when_api_returns_empty_data(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)
        ctx = _make_httpx_ctx(200, {"data": []})

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")

        assert "ch1" not in mod_bot._bot_is_mod

    async def test_does_not_add_on_401(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)
        ctx = _make_httpx_ctx(401, text="Unauthorized")

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")

        assert "ch1" not in mod_bot._bot_is_mod

    async def test_no_token_returns_early_without_error(self, mod_bot):
        mod_bot.channels.get_token = AsyncMock(return_value=None)

        await mod_bot._check_bot_mod_status("ch1")  # must not raise

        assert "ch1" not in mod_bot._bot_is_mod

    async def test_network_error_does_not_propagate(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")  # must not raise

        assert "ch1" not in mod_bot._bot_is_mod
