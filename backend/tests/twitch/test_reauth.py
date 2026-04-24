"""Tests for twitch.utils.reauth — is_scope_error and ReauthNotifier."""

from __future__ import annotations

import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from utils.reauth import ReauthNotifier, is_scope_error

# ---------------------------------------------------------------------------
# is_scope_error
# ---------------------------------------------------------------------------


class TestIsScopeError:
    def test_none_returns_false(self):
        assert is_scope_error(None) is False

    def test_non_401_with_scope_message_returns_false(self):
        class Resp:
            status_code = 403
            message = "Missing scope: channel:manage:moderators"

        assert is_scope_error(Resp()) is False

    def test_401_without_scope_message_returns_false(self):
        class Resp:
            status_code = 401
            message = "Invalid token"

        assert is_scope_error(Resp()) is False

    def test_401_with_scope_in_message_attr_returns_true(self):
        class Resp:
            status_code = 401
            message = "Missing scope: channel:manage:moderators"

        assert is_scope_error(Resp()) is True

    def test_twitchio_exception_uses_status_not_status_code(self):
        """TwitchIO HTTPException exposes .status (int), not .status_code."""

        class TwitchError:
            status = 401
            message = "Missing scope: moderator:manage:announcements"

        assert is_scope_error(TwitchError()) is True

    def test_json_body_with_scope_message_returns_true(self):
        """httpx.Response carries the message in its JSON body."""

        class Resp:
            status_code = 401

            def json(self):
                return {"message": "Missing scope: channel:read:subscriptions"}

        assert is_scope_error(Resp()) is True

    def test_json_body_without_scope_message_returns_false(self):
        class Resp:
            status_code = 401

            def json(self):
                return {"message": "Invalid OAuth token"}

        assert is_scope_error(Resp()) is False

    def test_stringified_fallback_returns_true(self):
        class Resp:
            status_code = 401

            def __str__(self):
                return "HTTPStatusError 401 Missing scope: bits:read"

        assert is_scope_error(Resp()) is True

    def test_200_response_returns_false(self):
        class Resp:
            status_code = 200
            message = "OK"

        assert is_scope_error(Resp()) is False

    def test_arbitrary_string_without_status_returns_false(self):
        assert is_scope_error("Missing scope: whatever") is False


# ---------------------------------------------------------------------------
# ReauthNotifier
# ---------------------------------------------------------------------------


class TestReauthNotifier:
    def _notifier(self) -> ReauthNotifier:
        return ReauthNotifier()

    async def test_first_call_sends_message_and_returns_true(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_message_mentions_broadcaster(self):
        notifier = self._notifier()
        captured: list[str] = []

        async def capture(msg: str) -> None:
            captured.append(msg)

        await notifier.notify("alice", "ch1", capture)
        assert captured
        assert "alice" in captured[0]

    async def test_message_contains_dashboard_path(self):
        notifier = self._notifier()
        captured: list[str] = []

        async def capture(msg: str) -> None:
            captured.append(msg)

        await notifier.notify("alice", "ch1", capture)
        assert "/docs/get-started" in captured[0]
        assert "niibot.tv" in captured[0]

    async def test_second_call_within_cooldown_skips_send(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", send_fn)
        send_fn.reset_mock()

        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is False
        send_fn.assert_not_awaited()

    async def test_send_allowed_after_cooldown_expires(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        # Back-date the last notification by more than 1 hour
        notifier._last_notified["ch1"] = datetime.now(UTC) - timedelta(hours=2)

        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_different_channels_have_independent_cooldowns(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", send_fn)

        result = await notifier.notify("bob", "ch2", send_fn)
        assert result is True
        assert send_fn.await_count == 2

    async def test_send_exception_does_not_propagate(self):
        """A broken send_fn must not crash the caller — notify still returns True."""
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is True

    async def test_cooldown_not_recorded_on_failed_send(self):
        """After a failed send, the cooldown timestamp is still set so we don't spam."""
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        await notifier.notify("alice", "ch1", send_fn)
        # The timestamp must have been recorded (cooldown enforced even on failure)
        assert "ch1" in notifier._last_notified
