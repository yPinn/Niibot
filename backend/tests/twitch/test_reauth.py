"""Tests for twitch.utils.reauth — is_scope_error and build_reauth_message."""

from __future__ import annotations

from unittest.mock import patch

from utils.reauth import build_reauth_message, is_scope_error

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
# build_reauth_message
# ---------------------------------------------------------------------------


class TestBuildReauthMessage:
    def test_message_mentions_broadcaster(self):
        with patch("utils.reauth.get_settings") as settings:
            settings.return_value.frontend_url = "https://niibot.tv"
            message = build_reauth_message("alice")
        assert "alice" in message

    def test_message_contains_frontend_url(self):
        with patch("utils.reauth.get_settings") as settings:
            settings.return_value.frontend_url = "https://niibot.tv"
            message = build_reauth_message("alice")
        assert "niibot.tv" in message

    def test_strips_trailing_slash_from_frontend_url(self):
        with patch("utils.reauth.get_settings") as settings:
            settings.return_value.frontend_url = "https://niibot.tv/"
            message = build_reauth_message("alice")
        assert "niibot.tv//login" not in message
        assert "niibot.tv/login" in message
