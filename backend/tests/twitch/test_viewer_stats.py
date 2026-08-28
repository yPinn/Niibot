"""Unit tests for twitch.components.viewer_stats — !followage / !subage / !subcount / !bits.

Invoke raw command callbacks via `.callback(component, ctx)` to bypass the
TwitchIO Command descriptor. `check_command` and `_helix_get` are mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.viewer_stats import ViewerStatsComponent, _humanise_since

pytestmark = pytest.mark.asyncio

PATCH_CHECK = "twitch.components.viewer_stats.check_command"


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    bot.channels.get_token = AsyncMock(return_value=MagicMock(token="TOK"))
    bot.bot_id = "bot-1"
    return bot


def _make_ctx(*, user_id="viewer-9", channel_id="chan-1", name="Viewer") -> MagicMock:
    ctx = MagicMock()
    ctx.chatter.id = user_id
    ctx.chatter.display_name = name
    ctx.chatter.name = name.lower()
    ctx.channel.id = channel_id
    ctx.channel.name = "streamer"
    return ctx


def _resp(status: int, payload: dict | None = None) -> MagicMock:
    r = MagicMock(status_code=status)
    r.json.return_value = payload or {}
    return r


@pytest.fixture()
def comp() -> ViewerStatsComponent:
    with patch("twitch.components.viewer_stats.get_settings") as gs:
        gs.return_value.twitch_client_id = "cid"
        c = ViewerStatsComponent(_make_bot())
    c._ctx_reply = AsyncMock()
    c._helix_get = AsyncMock()
    c.cmd_repo.increment_usage_count = AsyncMock()
    return c


async def _call(name: str, comp: ViewerStatsComponent, ctx: MagicMock) -> None:
    await getattr(ViewerStatsComponent, name).callback(comp, ctx)


# --------------------------------------------------------------------------- #
# _humanise_since
# --------------------------------------------------------------------------- #


async def test_humanise_since_days_only():
    assert _humanise_since(datetime.now(UTC) - timedelta(days=5)) == "5 天"


async def test_humanise_since_years_months():
    out = _humanise_since(datetime.now(UTC) - timedelta(days=400))
    assert "年" in out and "個月" in out


# --------------------------------------------------------------------------- #
# !followage — bot token, moderator_id = bot
# --------------------------------------------------------------------------- #


async def test_followage_uses_bot_token_and_reports_duration(comp):
    ctx = _make_ctx()
    followed = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    comp._helix_get.return_value = _resp(200, {"data": [{"followed_at": followed}]})

    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("followage", comp, ctx)

    comp.bot.channels.get_token.assert_awaited_with("bot-1", "bot")
    path, params, _token = comp._helix_get.await_args[0]
    assert path == "channels/followers"
    assert params["moderator_id"] == "bot-1"
    assert "已追隨" in comp._ctx_reply.await_args[0][1]


async def test_followage_not_following(comp):
    ctx = _make_ctx()
    comp._helix_get.return_value = _resp(200, {"data": []})
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("followage", comp, ctx)
    assert "還沒追隨" in comp._ctx_reply.await_args[0][1]


async def test_followage_disabled_command_is_silent(comp):
    ctx = _make_ctx()
    with patch(PATCH_CHECK, AsyncMock(return_value=None)):
        await _call("followage", comp, ctx)
    comp._ctx_reply.assert_not_called()
    comp._helix_get.assert_not_called()


# --------------------------------------------------------------------------- #
# !subage / !subcount — broadcaster token
# --------------------------------------------------------------------------- #


async def test_subage_reports_tier(comp):
    ctx = _make_ctx()
    comp._helix_get.return_value = _resp(200, {"data": [{"tier": "2000", "is_gift": False}]})
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("subage", comp, ctx)
    comp.bot.channels.get_token.assert_awaited_with("chan-1")
    assert "T2" in comp._ctx_reply.await_args[0][1]


async def test_subage_401_triggers_reauth(comp):
    ctx = _make_ctx()
    comp._helix_get.return_value = _resp(401)
    comp._notify_reauth = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("subage", comp, ctx)
    comp._notify_reauth.assert_awaited_once()


async def test_subcount_reports_total(comp):
    ctx = _make_ctx()
    comp._helix_get.return_value = _resp(200, {"total": 42})
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("subcount", comp, ctx)
    assert "42" in comp._ctx_reply.await_args[0][1]


# --------------------------------------------------------------------------- #
# !bits — broadcaster token
# --------------------------------------------------------------------------- #


async def test_bits_reports_rank(comp):
    ctx = _make_ctx()
    comp._helix_get.return_value = _resp(200, {"data": [{"rank": 3, "score": 5000}]})
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("bits", comp, ctx)
    msg = comp._ctx_reply.await_args[0][1]
    assert "3" in msg and "5000" in msg


async def test_bits_no_entry(comp):
    ctx = _make_ctx()
    comp._helix_get.return_value = _resp(200, {"data": []})
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("bits", comp, ctx)
    assert "還沒" in comp._ctx_reply.await_args[0][1]
