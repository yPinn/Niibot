"""Unit tests for EventComponent — currently just the fail-closed _get_message."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from twitch.components.events import EventComponent

pytestmark = pytest.mark.asyncio


def _component(config=None, *, raises=False):
    repo = SimpleNamespace()
    if raises:
        repo.get_config = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        repo.get_config = AsyncMock(return_value=config)
    bot = SimpleNamespace(event_configs=repo)
    return EventComponent(bot)


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
