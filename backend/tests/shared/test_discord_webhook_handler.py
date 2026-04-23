"""Unit tests for shared.discord_webhook_handler — DiscordWebhookHandler."""

from __future__ import annotations

import json
import logging
import sys
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from shared.discord_webhook_handler import (
    _LEVEL_COLORS,
    _LEVEL_EMOJI,
    DiscordWebhookHandler,
)


def _record(
    msg: str = "test error",
    level: int = logging.ERROR,
    name: str = "test.logger",
    exc_info=None,
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


class TestInit:
    def test_level_is_error(self):
        h = DiscordWebhookHandler("https://example.com/hook")
        assert h.level == logging.ERROR

    def test_default_service_name(self):
        h = DiscordWebhookHandler("https://example.com/hook")
        assert h._service == "niibot"

    def test_custom_service_name(self):
        h = DiscordWebhookHandler("https://example.com/hook", service_name="twitch")
        assert h._service == "twitch"


class TestBuildPayload:
    def setup_method(self):
        self.h = DiscordWebhookHandler("https://example.com/hook", service_name="api")

    def test_returns_bytes(self):
        assert isinstance(self.h._build_payload(_record()), bytes)

    def test_payload_is_valid_json(self):
        data = json.loads(self.h._build_payload(_record()))
        assert "embeds" in data

    def test_embed_title_contains_service_uppercased(self):
        data = json.loads(self.h._build_payload(_record()))
        assert "API" in data["embeds"][0]["title"]

    def test_embed_title_contains_level_name(self):
        data = json.loads(self.h._build_payload(_record(level=logging.ERROR)))
        assert "ERROR" in data["embeds"][0]["title"]

    def test_embed_description_contains_message(self):
        data = json.loads(self.h._build_payload(_record(msg="db timeout")))
        assert "db timeout" in data["embeds"][0]["description"]

    def test_error_color(self):
        data = json.loads(self.h._build_payload(_record(level=logging.ERROR)))
        assert data["embeds"][0]["color"] == _LEVEL_COLORS[logging.ERROR]

    def test_critical_color(self):
        data = json.loads(self.h._build_payload(_record(level=logging.CRITICAL)))
        assert data["embeds"][0]["color"] == _LEVEL_COLORS[logging.CRITICAL]

    def test_warning_color(self):
        data = json.loads(self.h._build_payload(_record(level=logging.WARNING)))
        assert data["embeds"][0]["color"] == _LEVEL_COLORS[logging.WARNING]

    def test_logger_name_in_fields(self):
        data = json.loads(self.h._build_payload(_record(name="discord.events")))
        fields = {f["name"]: f["value"] for f in data["embeds"][0]["fields"]}
        assert fields["Logger"] == "discord.events"
        assert fields["Service"] == "api"

    def test_exc_info_appended_as_code_block(self):
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        data = json.loads(self.h._build_payload(_record(exc_info=exc_info)))
        desc = data["embeds"][0]["description"]
        assert "```" in desc
        assert "ValueError" in desc

    def test_long_message_capped_at_4096(self):
        data = json.loads(self.h._build_payload(_record(msg="x" * 5000)))
        assert len(data["embeds"][0]["description"]) <= 4096

    def test_embed_emoji_in_title(self):
        data = json.loads(self.h._build_payload(_record(level=logging.ERROR)))
        assert _LEVEL_EMOJI[logging.ERROR] in data["embeds"][0]["title"]


class TestPost:
    def test_calls_urlopen_with_payload(self):
        h = DiscordWebhookHandler("https://example.com/hook")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=ctx) as mock_open:
            h._post(b'{"test": true}')
            mock_open.assert_called_once()

    def test_swallows_network_errors(self):
        h = DiscordWebhookHandler("https://example.com/hook")
        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            h._post(b"payload")  # must not raise


class TestEmit:
    def test_submits_to_executor(self):
        h = DiscordWebhookHandler("https://example.com/hook")
        f: Future[None] = Future()
        f.set_result(None)
        with patch.object(h._executor, "submit", return_value=f) as mock_submit:
            h.emit(_record())
            mock_submit.assert_called_once()

    def test_build_failure_calls_handle_error(self):
        h = DiscordWebhookHandler("https://example.com/hook")
        with patch.object(h, "_build_payload", side_effect=RuntimeError("bad")):
            with patch.object(h, "handleError") as mock_handle:
                h.emit(_record())
                mock_handle.assert_called_once()
