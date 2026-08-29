"""Unit tests for EventsComponent — _get_template (fail-closed) and _notify."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.events import EventsComponent

pytestmark = pytest.mark.asyncio


def _component(config=None, *, raises=False, is_mod=True):
    repo = SimpleNamespace()
    if raises:
        repo.get_config = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        repo.get_config = AsyncMock(return_value=config)

    partial = SimpleNamespace(send_message=AsyncMock())
    bot = SimpleNamespace(
        event_configs=repo,
        bot_id="bot-1",
        _bot_is_mod={"ch"} if is_mod else set(),
        create_partialuser=MagicMock(return_value=partial),
    )
    comp = EventsComponent(bot)
    comp._sent_partial = partial  # test handle for the channel's send_message
    return comp


class TestGetTemplate:
    async def test_missing_config_returns_none(self):
        assert await _component(config=None)._get_template("ch", "follow") is None

    async def test_disabled_config_returns_none(self):
        cfg = SimpleNamespace(enabled=False, message_template="hi")
        assert await _component(config=cfg)._get_template("ch", "follow") is None

    async def test_db_error_returns_none(self):
        assert await _component(raises=True)._get_template("ch", "follow") is None

    async def test_enabled_returns_raw_template(self):
        cfg = SimpleNamespace(enabled=True, message_template="hi $(user)")
        assert await _component(config=cfg)._get_template("ch", "follow") == "hi $(user)"


class TestNotify:
    async def test_not_mod_is_silent(self):
        cfg = SimpleNamespace(enabled=True, message_template="hi $(user)")
        comp = _component(config=cfg, is_mod=False)
        assert await comp._notify("ch", "follow", {"user": "A"}, label="x") is False
        comp._sent_partial.send_message.assert_not_awaited()

    async def test_disabled_is_silent(self):
        comp = _component(config=None)
        assert await comp._notify("ch", "follow", {"user": "A"}, label="x") is False
        comp._sent_partial.send_message.assert_not_awaited()

    async def test_sends_rendered_message(self):
        cfg = SimpleNamespace(enabled=True, message_template="hi $(user)")
        comp = _component(config=cfg)
        assert await comp._notify("ch", "follow", {"user": "A"}, label="x") is True
        comp._sent_partial.send_message.assert_awaited_once_with(message="hi A", sender="bot-1")

    async def test_send_failure_returns_false(self):
        cfg = SimpleNamespace(enabled=True, message_template="hi")
        comp = _component(config=cfg)
        comp._sent_partial.send_message.side_effect = RuntimeError("rate limited")
        assert await comp._notify("ch", "follow", {}, label="x") is False
