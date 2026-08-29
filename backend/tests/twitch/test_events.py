"""Unit tests for EventComponent — _get_message and _clean_message_var."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from twitch.components.events import _MESSAGE_VAR_LIMIT, EventComponent, _clean_message_var


class TestCleanMessageVar:
    def test_collapses_newlines_and_whitespace(self):
        assert _clean_message_var("hi\n\nthere   world") == "hi there world"

    def test_drops_leading_command_char(self):
        assert _clean_message_var("/me waves") == "me waves"
        assert _clean_message_var(".timeout bob") == "timeout bob"
        assert _clean_message_var("...anyway") == "..anyway"  # only the first char

    def test_caps_length(self):
        assert len(_clean_message_var("x" * 999)) == _MESSAGE_VAR_LIMIT

    def test_plain_text_untouched(self):
        assert _clean_message_var("thanks for the sub!") == "thanks for the sub!"


def _component(config=None, *, raises=False):
    repo = SimpleNamespace()
    if raises:
        repo.get_config = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        repo.get_config = AsyncMock(return_value=config)
    bot = SimpleNamespace(event_configs=repo)
    return EventComponent(bot)


@pytest.mark.asyncio
class TestGetMessage:
    async def test_missing_config_stays_silent(self):
        comp = _component(config=None)
        assert await comp._get_message("ch", "follow", {"user": "A"}) is None

    async def test_disabled_config_stays_silent(self):
        cfg = SimpleNamespace(enabled=False, message_template="hi $(user)")
        comp = _component(config=cfg)
        assert await comp._get_message("ch", "follow", {"user": "A"}) is None

    async def test_db_error_stays_silent(self):
        comp = _component(raises=True)
        assert await comp._get_message("ch", "follow", {"user": "A"}) is None

    async def test_enabled_config_renders_variables(self):
        cfg = SimpleNamespace(enabled=True, message_template="感謝 $(user) $(tier)")
        comp = _component(config=cfg)
        msg = await comp._get_message("ch", "subscribe", {"user": "A", "tier": "T2"})
        assert msg == "感謝 A T2"
