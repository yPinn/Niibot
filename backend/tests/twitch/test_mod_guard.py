"""Tests for twitch.utils.mod_guard — build_mod_request_message."""

from __future__ import annotations

from utils.mod_guard import build_mod_request_message


class TestBuildModRequestMessage:
    def test_mentions_broadcaster_and_bot_login(self):
        msg = build_mod_request_message("alice", "niibot_")
        assert "alice" in msg
        assert "niibot_" in msg

    def test_different_logins_produce_different_messages(self):
        assert build_mod_request_message("alice", "niibot_") != build_mod_request_message(
            "bob", "niibot_"
        )
