"""Unit tests for twitch.components.tft — !tft argument handling.

Scraping is stubbed (`get_leaderboard_data` / `get_player_data`); these cover
how the typed Riot ID is parsed, not tactics.tools.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.tft import TftComponent

pytestmark = pytest.mark.asyncio

PATCH_CHECK = "twitch.components.tft.check_command"

_LEADERBOARD = {
    "thresholds": [900, 700],
    "entries": [{"playerName": "Foo Bar#TW2", "num": 12, "rank": ["MASTER", 345]}],
}


@pytest.fixture()
def comp() -> TftComponent:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    c = TftComponent(bot)
    c._ctx_reply = AsyncMock()
    c.cmd_repo.increment_usage_count = AsyncMock()
    c.get_leaderboard_data = AsyncMock(return_value=_LEADERBOARD)
    c.get_player_data = AsyncMock(return_value=None)
    return c


async def _tft(comp: TftComponent, user_id: str | None) -> str:
    ctx = MagicMock()
    ctx.channel.id = "chan-1"
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await TftComponent.tft.callback(comp, ctx, user_id=user_id)
    return comp._ctx_reply.await_args[0][1]


@pytest.mark.parametrize("user_id", [None, "", "  ", ";'"])
async def test_no_player_shows_thresholds(comp, user_id):
    assert "菁英：900 LP" in await _tft(comp, user_id)
    comp.get_player_data.assert_not_called()


@pytest.mark.parametrize(
    "user_id",
    ["Foo Bar#TW2", "foo bar#tw2", "Foo Bar #TW2", "Foo Bar＃TW2", ";Foo  Bar#TW2'"],
)
async def test_riot_id_with_spaces_matches_leaderboard(comp, user_id):
    reply = await _tft(comp, user_id)
    assert "[TW] #12" in reply
    comp.get_player_data.assert_not_called()


async def test_player_page_receives_name_with_spaces(comp):
    comp.get_player_data.return_value = {"tier": "GOLD", "rank": "II", "leaguePoints": 50}
    reply = await _tft(comp, "Some Player#ABC1")
    comp.get_player_data.assert_awaited_once_with("Some Player", "ABC1")
    assert "金牌 II 50 LP" in reply


@pytest.mark.parametrize("user_id", ["Foo", "#TW2", "Foo#", "Foo# ;"])
async def test_malformed_riot_id_gets_format_hint(comp, user_id):
    assert "請使用正確格式" in await _tft(comp, user_id)
    comp.get_player_data.assert_not_called()


async def test_unknown_player(comp):
    assert "找不到玩家：Nobody#TW9" in await _tft(comp, "Nobody#TW9")
