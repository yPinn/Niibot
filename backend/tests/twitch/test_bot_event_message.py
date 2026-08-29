"""Unit tests for Bot.event_message and _check_bot_mod_status."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subs(subscribed=(), *, bot_id="bot-001"):
    """Real SubscriptionManager with mocked transport for Bot.subs."""
    from twitch.core.subscription_manager import SubscriptionManager

    m = SubscriptionManager(
        bot_id=bot_id,
        multi_subscribe=AsyncMock(),
        delete_subscription=AsyncMock(),
        needs_reauth=set(),
    )
    m._subscribed = set(subscribed)
    return m


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
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b.subs = _make_subs({"123"})
        b.sessions = MagicMock()
        b.sessions.record_line = MagicMock()
        b._bot_id = "bot-001"
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
async def test_channel_bound_into_log_context_during_handling(bot):
    """The broadcaster name/id is visible in the log context while the
    message is processed (so every downstream log line carries it)."""
    import structlog

    seen: dict = {}

    async def _capture(_payload):
        seen.update(structlog.contextvars.get_contextvars())
        return False

    bot._handle_custom_command = _capture
    payload = _make_payload(broadcaster_name="streamer_a", broadcaster_id="123", text="hi")

    with patch("twitch.core.bot.commands.AutoBot.event_message", new=AsyncMock()):
        await bot.event_message(payload)

    assert seen.get("channel") == "streamer_a"
    assert seen.get("channel_id") == "123"
    # and it does not leak after the handler returns
    assert "channel" not in structlog.contextvars.get_contextvars()


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
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._bot_id = "bot-001"
        b._client_id = "client-abc"
        b._needs_reauth = set()
        b._bot_is_mod = set()
        b._mod_check_pending = set()
        b.subs = _make_subs()
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


# ---------------------------------------------------------------------------
# Tests — event_token_refreshed mod-check dedup
# ---------------------------------------------------------------------------


def _make_bot_for_token_refresh(needs_reauth: set[str] | None = None):
    """Minimal Bot instance for event_token_refreshed tests."""
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._bot_id = "bot-001"
        b.subs = _make_subs()
        b._needs_reauth = needs_reauth if needs_reauth is not None else set()
        b._bot_is_mod = set()
        b._token_refresh_buffer = []
        b._token_refresh_flush_task = None
        b._background_tasks = set()
        b.channels = MagicMock()
        b.channels.upsert_token_only = AsyncMock()
        b._check_bot_mod_status = AsyncMock()
        return b


def _make_refresh_payload(user_id: str):
    p = MagicMock()
    p.user_id = user_id
    p.token = "new-tok"
    p.refresh_token = "new-refresh"
    p.scopes = ["chat:read"]
    return p


@pytest.mark.asyncio
async def test_token_refresh_skips_mod_check_when_needs_reauth():
    """Channel already flagged for reauth → mod check is skipped on refresh (no 401 log spam)."""
    b = _make_bot_for_token_refresh(needs_reauth={"123"})

    await b.event_token_refreshed(_make_refresh_payload("123"))

    b._check_bot_mod_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_refresh_triggers_mod_check_when_not_mod_and_not_reauth():
    """Channel not mod and not in reauth → mod check runs (covers new channels)."""
    b = _make_bot_for_token_refresh(needs_reauth=set())

    await b.event_token_refreshed(_make_refresh_payload("123"))

    b._check_bot_mod_status.assert_awaited_once_with("123")


@pytest.mark.asyncio
async def test_token_refresh_skips_mod_check_when_already_mod():
    """Channel confirmed mod → no need to re-check."""
    b = _make_bot_for_token_refresh()
    b._bot_is_mod = {"123"}

    await b.event_token_refreshed(_make_refresh_payload("123"))

    b._check_bot_mod_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_refresh_batches_burst_into_single_log_line(caplog):
    """Multiple refreshes within the debounce window produce one summary INFO line."""
    import asyncio
    import logging

    b = _make_bot_for_token_refresh()
    b._ch = lambda uid: f"name{uid}({uid})"  # stub _ch for predictable output

    with patch("twitch.core.bot.asyncio.sleep", new=AsyncMock()):
        # Three refreshes back-to-back; each cancels the previous flush task.
        await b.event_token_refreshed(_make_refresh_payload("u1"))
        await b.event_token_refreshed(_make_refresh_payload("u2"))
        await b.event_token_refreshed(_make_refresh_payload("u3"))

        # Drain whichever flush task survived (cancelled ones raise CancelledError silently).
        pending = [t for t in b._background_tasks if not t.done()]
        with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
            await asyncio.gather(*pending, return_exceptions=True)

    summary = [r for r in caplog.records if r.message.startswith("Token refresh:")]
    assert len(summary) == 1
    assert "3 channels" in summary[0].message
    assert "u1" in summary[0].message and "u3" in summary[0].message


# ---------------------------------------------------------------------------
# Tests — Shared Chat session tracking
# ---------------------------------------------------------------------------


def _make_shared_chat_bot():
    """Minimal Bot for shared-chat event tests."""
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._shared_chat_sessions = {}
        return b


def _make_shared_chat_payload(
    *,
    broadcaster_id: str,
    broadcaster_name: str,
    host_id: str,
    host_name: str,
    session_id: str = "sess-1",
    participants: list[tuple[str, str]] | None = None,
):
    payload = MagicMock()
    payload.broadcaster = _make_partial_user(broadcaster_id, broadcaster_name)
    payload.host = _make_partial_user(host_id, host_name)
    payload.session_id = session_id
    payload.participants = [_make_partial_user(pid, name) for pid, name in (participants or [])]
    return payload


def _make_session(
    *,
    session_id: str = "sess-1",
    host_id: str = "999",
    host_name: str = "other_host",
    participants: tuple[tuple[str, str], ...] = (("999", "other_host"), ("123", "ours")),
    our_channel_ids: tuple[str, ...] = ("123",),
):
    from datetime import UTC, datetime

    from twitch.core.bot import SharedChatSession

    return SharedChatSession(
        session_id=session_id,
        host_id=host_id,
        host_name=host_name,
        participants=participants,
        started_at=datetime.now(UTC),
        our_channel_ids=our_channel_ids,
    )


@pytest.mark.asyncio
async def test_shared_chat_begin_stores_session_keyed_by_session_id(caplog):
    import logging

    b = _make_shared_chat_bot()
    payload = _make_shared_chat_payload(
        broadcaster_id="123",
        broadcaster_name="ours",
        host_id="999",
        host_name="other_host",
        session_id="sess-1",
        participants=[("999", "other_host"), ("123", "ours"), ("555", "third")],
    )

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_begin(payload)

    session = b._shared_chat_sessions["sess-1"]
    assert session.our_channel_ids == ("123",)
    assert ("555", "third") in session.participants

    msgs = [r.message for r in caplog.records if "SharedChat begin" in r.message]
    assert len(msgs) == 1
    assert "session=sess-1" in msgs[0]
    assert "other_host(host)" in msgs[0]
    assert "ours(self)" in msgs[0]


@pytest.mark.asyncio
async def test_shared_chat_begin_dedups_when_second_of_our_channels_joins(caplog):
    import logging

    b = _make_shared_chat_bot()
    payload_a = _make_shared_chat_payload(
        broadcaster_id="123",
        broadcaster_name="ours_a",
        host_id="999",
        host_name="other_host",
        session_id="sess-1",
        participants=[("999", "other_host"), ("123", "ours_a")],
    )
    payload_b = _make_shared_chat_payload(
        broadcaster_id="456",
        broadcaster_name="ours_b",
        host_id="999",
        host_name="other_host",
        session_id="sess-1",
        participants=[("999", "other_host"), ("123", "ours_a"), ("456", "ours_b")],
    )

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_begin(payload_a)
        await b.event_shared_chat_begin(payload_b)

    begin_msgs = [r.message for r in caplog.records if "SharedChat begin" in r.message]
    assert len(begin_msgs) == 1  # second begin is silent
    assert b._shared_chat_sessions["sess-1"].our_channel_ids == ("123", "456")


@pytest.mark.asyncio
async def test_shared_chat_update_logs_diff_only_from_canonical(caplog):
    import logging

    b = _make_shared_chat_bot()
    b._shared_chat_sessions["sess-1"] = _make_session(
        participants=(("999", "other_host"), ("123", "ours_a"), ("456", "ours_b")),
        our_channel_ids=("123", "456"),
    )

    payload_from_canonical = _make_shared_chat_payload(
        broadcaster_id="123",
        broadcaster_name="ours_a",
        host_id="999",
        host_name="other_host",
        session_id="sess-1",
        participants=[
            ("999", "other_host"),
            ("123", "ours_a"),
            ("456", "ours_b"),
            ("777", "newcomer"),
        ],
    )
    payload_from_non_canonical = _make_shared_chat_payload(
        broadcaster_id="456",
        broadcaster_name="ours_b",
        host_id="999",
        host_name="other_host",
        session_id="sess-1",
        participants=[
            ("999", "other_host"),
            ("123", "ours_a"),
            ("456", "ours_b"),
            ("777", "newcomer"),
        ],
    )

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_update(payload_from_non_canonical)
        await b.event_shared_chat_update(payload_from_canonical)

    update_msgs = [r.message for r in caplog.records if "SharedChat update" in r.message]
    # Only canonical (123) logs — but it runs second, and by then state already updated
    # by the non-canonical call, so its diff is empty → no log emitted.
    # First call (non-canonical) is silenced by design.
    assert len(update_msgs) == 0


@pytest.mark.asyncio
async def test_shared_chat_update_canonical_logs_membership_diff(caplog):
    import logging

    b = _make_shared_chat_bot()
    b._shared_chat_sessions["sess-1"] = _make_session(
        participants=(("999", "other_host"), ("123", "ours")),
        our_channel_ids=("123",),
    )
    payload = _make_shared_chat_payload(
        broadcaster_id="123",
        broadcaster_name="ours",
        host_id="999",
        host_name="other_host",
        session_id="sess-1",
        participants=[("999", "other_host"), ("123", "ours"), ("777", "newcomer")],
    )

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_update(payload)

    update_msgs = [r.message for r in caplog.records if "SharedChat update" in r.message]
    assert len(update_msgs) == 1
    assert "+newcomer" in update_msgs[0]
    assert "session=sess-1" in update_msgs[0]


@pytest.mark.asyncio
async def test_shared_chat_end_logs_only_when_last_of_our_channels_leaves(caplog):
    import logging

    b = _make_shared_chat_bot()
    b._shared_chat_sessions["sess-1"] = _make_session(
        participants=(("999", "other_host"), ("123", "ours_a"), ("456", "ours_b")),
        our_channel_ids=("123", "456"),
    )

    end_a = MagicMock()
    end_a.broadcaster = _make_partial_user("123", "ours_a")
    end_a.session_id = "sess-1"
    end_b = MagicMock()
    end_b.broadcaster = _make_partial_user("456", "ours_b")
    end_b.session_id = "sess-1"

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_end(end_a)
        # After A leaves, session still present (B still in)
        assert "sess-1" in b._shared_chat_sessions
        await b.event_shared_chat_end(end_b)

    end_msgs = [r.message for r in caplog.records if "SharedChat end" in r.message]
    assert len(end_msgs) == 1
    assert "sess-1" not in b._shared_chat_sessions
    assert "duration=" in end_msgs[0]


@pytest.mark.asyncio
async def test_shared_chat_end_without_tracked_session_logs_bare(caplog):
    """End arrives for a session we never tracked (bot restart) — log a bare end."""
    import logging

    b = _make_shared_chat_bot()
    payload = MagicMock()
    payload.broadcaster = _make_partial_user("123", "ours")
    payload.session_id = "orphan-sess"

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_end(payload)

    msgs = [r.message for r in caplog.records if "SharedChat end" in r.message]
    assert len(msgs) == 1
    assert "session=orphan-sess" in msgs[0]
    assert "duration=" not in msgs[0]


@pytest.mark.asyncio
async def test_shared_chat_update_without_prior_begin_synthesizes_and_logs_begin(caplog):
    """Update arriving before Begin (race) synthesizes the session and logs as begin."""
    import logging

    b = _make_shared_chat_bot()
    payload = _make_shared_chat_payload(
        broadcaster_id="123",
        broadcaster_name="ours",
        host_id="999",
        host_name="other_host",
        session_id="sess-x",
        participants=[("999", "other_host"), ("123", "ours")],
    )

    with caplog.at_level(logging.INFO, logger="twitch.core.bot"):
        await b.event_shared_chat_update(payload)

    assert "sess-x" in b._shared_chat_sessions
    begin_msgs = [r.message for r in caplog.records if "SharedChat begin" in r.message]
    assert len(begin_msgs) == 1
