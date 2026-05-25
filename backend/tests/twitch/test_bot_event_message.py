"""Unit tests for Bot.event_message and _check_bot_mod_status."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_partial_user(user_id: str, name: str):
    u = MagicMock()
    u.id = user_id
    u.name = name
    return u


def _make_payload(
    *,
    broadcaster_id: str = "123",
    broadcaster_name: str = "streamer_a",
    chatter_id: str = "456",
    chatter_name: str = "viewer",
    text: str = "hello",
    source_broadcaster=None,
    reply=None,
):
    """Build a minimal ChatMessage-like mock."""
    payload = MagicMock()
    payload.broadcaster = _make_partial_user(broadcaster_id, broadcaster_name)
    payload.chatter = _make_partial_user(chatter_id, chatter_name)
    payload.chatter.display_name = chatter_name
    payload.text = text
    payload.source_broadcaster = source_broadcaster
    payload.reply = reply
    payload.id = "msg-001"
    return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bot():
    """Return a Bot instance with all heavy deps mocked out."""
    with (
        patch("twitch.core.bot._ChannelMixin.__init__", return_value=None),
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot._SessionMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._subscribed_channels = {"123"}
        b._bot_id = "bot-001"
        b._active_sessions = {}
        b._chatter_buffers = {}
        b._channel_line_counts = {}
        b._needs_reauth = set()
        b._bot_is_mod = {"123"}
        b._mod_check_pending = set()
        b._bot_login = "niibot_test"
        b._handle_custom_command = AsyncMock(return_value=False)
        b._handle_message_trigger = AsyncMock(return_value=False)
        b._background_tasks = set()
        return b


# ---------------------------------------------------------------------------
# Tests — shared-chat filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_chat_message_is_skipped(bot):
    """Messages from a shared-chat partner (source_broadcaster set) must be ignored."""
    source = _make_partial_user("999", "streamer_b")
    payload = _make_payload(source_broadcaster=source)

    with patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock:
        await bot.event_message(payload)

    bot._handle_custom_command.assert_not_called()
    bot._handle_message_trigger.assert_not_called()
    super_mock.assert_not_called()


@pytest.mark.asyncio
async def test_own_channel_message_is_processed(bot):
    """Messages from the broadcaster's own channel (source_broadcaster=None) are processed."""
    payload = _make_payload(source_broadcaster=None, text="!hello")

    with patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock:
        await bot.event_message(payload)

    bot._handle_custom_command.assert_called_once_with(payload)
    super_mock.assert_called_once_with(payload)


@pytest.mark.asyncio
async def test_unsubscribed_channel_is_blocked(bot):
    """Messages from a channel not in _subscribed_channels are dropped before shared-chat check."""
    payload = _make_payload(broadcaster_id="999")  # not in bot._subscribed_channels

    with patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock:
        await bot.event_message(payload)

    bot._handle_custom_command.assert_not_called()
    super_mock.assert_not_called()


@pytest.mark.asyncio
async def test_bot_own_message_is_ignored(bot):
    """The bot must not react to its own messages to prevent self-triggering loops."""
    payload = _make_payload(chatter_id="bot-001", source_broadcaster=None, text="!hi")

    with patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock:
        await bot.event_message(payload)

    bot._handle_custom_command.assert_not_called()
    super_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — mod guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_blocked_when_bot_not_mod(bot):
    """All command routing is skipped and mod_guard_notifier fires when bot lacks mod."""
    bot._bot_is_mod = set()  # bot has no mod in any channel
    payload = _make_payload(source_broadcaster=None, text="!hello")

    with (
        patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock,
        patch("twitch.core.bot.mod_guard_notifier") as mock_notifier,
    ):
        mock_notifier.notify = AsyncMock(return_value=True)
        await bot.event_message(payload)

    mock_notifier.notify.assert_awaited_once()
    bot._handle_custom_command.assert_not_called()
    super_mock.assert_not_called()


@pytest.mark.asyncio
async def test_message_passes_when_bot_has_mod(bot):
    """Command routing runs normally when bot has confirmed mod in the channel."""
    assert "123" in bot._bot_is_mod  # fixture default
    payload = _make_payload(source_broadcaster=None, text="!hello")

    with patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock:
        await bot.event_message(payload)

    bot._handle_custom_command.assert_called_once_with(payload)
    super_mock.assert_called_once_with(payload)


# ---------------------------------------------------------------------------
# Tests — reauth guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reauth_notifier_fires_and_blocks_processing(bot):
    """When channel needs reauth, only the reauth notifier fires; mod guard and commands are skipped."""
    bot._needs_reauth = {"123"}
    payload = _make_payload(source_broadcaster=None, text="!hello")

    with (
        patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()) as super_mock,
        patch("twitch.core.bot.mod_guard_notifier") as mock_mod_guard,
        patch("utils.reauth.reauth_notifier") as mock_reauth,
    ):
        mock_reauth.notify = AsyncMock(return_value=True)
        mock_mod_guard.notify = AsyncMock(return_value=True)
        await bot.event_message(payload)

    mock_reauth.notify.assert_awaited_once()
    mock_mod_guard.notify.assert_not_called()
    bot._handle_custom_command.assert_not_called()
    super_mock.assert_not_called()


@pytest.mark.asyncio
async def test_reauth_takes_priority_over_mod_guard(bot):
    """When channel needs reauth AND bot lacks mod, reauth fires — mod guard stays silent."""
    bot._needs_reauth = {"123"}
    bot._bot_is_mod = set()  # bot also not mod
    payload = _make_payload(source_broadcaster=None, text="!hello")

    with (
        patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()),
        patch("twitch.core.bot.mod_guard_notifier") as mock_mod_guard,
        patch("utils.reauth.reauth_notifier") as mock_reauth,
    ):
        mock_reauth.notify = AsyncMock(return_value=True)
        mock_mod_guard.notify = AsyncMock(return_value=True)
        await bot.event_message(payload)

    mock_reauth.notify.assert_awaited_once()
    mock_mod_guard.notify.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — _check_bot_mod_status reauth detection
# ---------------------------------------------------------------------------


def _make_bot_for_mod_check():
    """Minimal Bot instance for _check_bot_mod_status tests."""
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
        b._client_id = "client-abc"
        b._channel_names = {}
        b._needs_reauth = set()
        b._bot_is_mod = set()
        b._mod_check_pending = set()
        token = MagicMock()
        token.token = "tok"
        b.channels = MagicMock()
        b.channels.get_token = AsyncMock(return_value=token)
        return b


@pytest.mark.asyncio
async def test_mod_check_200_with_data_adds_to_bot_is_mod():
    """200 response with data → channel added to _bot_is_mod."""
    b = _make_bot_for_mod_check()
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"data": [{"user_id": "bot-001"}]}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(return_value=resp)
        await b._check_bot_mod_status("123")

    assert "123" in b._bot_is_mod
    assert "123" not in b._needs_reauth


@pytest.mark.asyncio
async def test_mod_check_200_empty_data_leaves_not_mod():
    """200 response with empty data → channel stays out of _bot_is_mod."""
    b = _make_bot_for_mod_check()
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"data": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(return_value=resp)
        await b._check_bot_mod_status("123")

    assert "123" not in b._bot_is_mod
    assert "123" not in b._needs_reauth


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_mod_check_auth_failure_marks_needs_reauth(status_code):
    """401 or 403 from Helix → channel added to _needs_reauth, NOT _bot_is_mod."""
    b = _make_bot_for_mod_check()
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = "Unauthorized"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(return_value=resp)
        await b._check_bot_mod_status("123")

    assert "123" in b._needs_reauth
    assert "123" not in b._bot_is_mod
