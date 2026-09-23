"""Unit tests for twitch.components.channel_info — !title / !game / !tags / !marker.

Invoke raw command callbacks via `.callback(component, ctx)` to bypass the
TwitchIO Command descriptor. `check_command` and `ctx.broadcaster` are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.channel_info import ChannelInfoComponent

pytestmark = pytest.mark.asyncio

PATCH_CHECK = "twitch.components.channel_info.check_command"


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    return bot


def _make_ctx(*, is_moderator: bool = False) -> MagicMock:
    ctx = MagicMock()
    ctx.chatter.broadcaster = False
    ctx.chatter.moderator = is_moderator
    ctx.chatter.vip = False
    ctx.chatter.subscriber = False
    ctx.channel.id = "chan-1"
    ctx.channel.name = "streamer"
    ctx.broadcaster = AsyncMock()
    return ctx


@pytest.fixture(autouse=True)
def _reset_command_failure_debounce():
    """command_failure_notifier is a process-wide singleton; clear its debounce
    state so one test's failure reply doesn't silence the next test's."""
    from utils.command_failure import command_failure_notifier

    command_failure_notifier._last_notified.clear()
    yield
    command_failure_notifier._last_notified.clear()


@pytest.fixture()
def comp() -> ChannelInfoComponent:
    c = ChannelInfoComponent(_make_bot())
    c._ctx_reply = AsyncMock()
    c.cmd_repo.increment_usage_count = AsyncMock()
    return c


async def _call(name: str, comp: ChannelInfoComponent, ctx: MagicMock, **kwargs) -> None:
    await getattr(ChannelInfoComponent, name).callback(comp, ctx, **kwargs)


# --------------------------------------------------------------------------- #
# !title — read
# --------------------------------------------------------------------------- #


async def test_title_read_reports_current_title(comp):
    ctx = _make_ctx()
    ctx.broadcaster.fetch_channel_info = AsyncMock(return_value=MagicMock(title="晚安直播"))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("title", comp, ctx)
    assert "晚安直播" in comp._ctx_reply.await_args[0][1]
    ctx.broadcaster.modify_channel.assert_not_called()


async def test_title_read_failure_is_generic(comp):
    ctx = _make_ctx()
    ctx.broadcaster.fetch_channel_info = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("title", comp, ctx)
    assert "查詢失敗" in comp._ctx_reply.await_args[0][1]


async def test_title_disabled_command_is_silent(comp):
    ctx = _make_ctx()
    with patch(PATCH_CHECK, AsyncMock(return_value=None)):
        await _call("title", comp, ctx)
    comp._ctx_reply.assert_not_called()
    ctx.broadcaster.fetch_channel_info.assert_not_called()


# --------------------------------------------------------------------------- #
# !title <new title> — write, moderator+ only
# --------------------------------------------------------------------------- #


async def test_title_write_requires_moderator(comp):
    ctx = _make_ctx(is_moderator=False)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("title", comp, ctx, new_title="新標題")
    assert "Mod" in comp._ctx_reply.await_args[0][1]
    ctx.broadcaster.modify_channel.assert_not_called()


async def test_title_write_updates_as_moderator(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.modify_channel = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("title", comp, ctx, new_title="新標題")
    ctx.broadcaster.modify_channel.assert_awaited_once_with(title="新標題")
    assert "新標題" in comp._ctx_reply.await_args[0][1]
    comp.cmd_repo.increment_usage_count.assert_awaited_once_with("chan-1", "title")


async def test_title_write_scope_error_triggers_reauth(comp):
    ctx = _make_ctx(is_moderator=True)
    err = RuntimeError("Request failed with status 401: Missing scope: channel:manage:broadcast")
    err.status = 401
    ctx.broadcaster.modify_channel = AsyncMock(side_effect=err)
    comp._notify_reauth = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("title", comp, ctx, new_title="新標題")
    comp._notify_reauth.assert_awaited_once()


async def test_title_write_generic_failure(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.modify_channel = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("title", comp, ctx, new_title="新標題")
    assert "修改標題失敗" in comp._ctx_reply.await_args[0][1]


# --------------------------------------------------------------------------- #
# !game — read
# --------------------------------------------------------------------------- #


async def test_game_read_reports_current_game(comp):
    ctx = _make_ctx()
    ctx.broadcaster.fetch_channel_info = AsyncMock(
        return_value=MagicMock(game_name="Just Chatting")
    )
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("game", comp, ctx)
    assert "Just Chatting" in comp._ctx_reply.await_args[0][1]


async def test_game_read_reports_unset(comp):
    ctx = _make_ctx()
    ctx.broadcaster.fetch_channel_info = AsyncMock(return_value=MagicMock(game_name=""))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("game", comp, ctx)
    assert "尚未設定" in comp._ctx_reply.await_args[0][1]


# --------------------------------------------------------------------------- #
# !game <name> — write, moderator+ only
# --------------------------------------------------------------------------- #


async def test_game_write_requires_moderator(comp):
    ctx = _make_ctx(is_moderator=False)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("game", comp, ctx, new_game="Just Chatting")
    assert "Mod" in comp._ctx_reply.await_args[0][1]
    comp.bot.fetch_games.assert_not_called()


async def test_game_write_updates_as_moderator(comp):
    ctx = _make_ctx(is_moderator=True)
    comp.bot.fetch_games = AsyncMock(return_value=[MagicMock(id="509658", name="Just Chatting")])
    ctx.broadcaster.modify_channel = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("game", comp, ctx, new_game="just chatting")
    comp.bot.fetch_games.assert_awaited_once_with(names=["just chatting"])
    ctx.broadcaster.modify_channel.assert_awaited_once_with(game_id="509658")
    assert "Just Chatting" in comp._ctx_reply.await_args[0][1]
    comp.cmd_repo.increment_usage_count.assert_awaited_once_with("chan-1", "game")


async def test_game_write_not_found(comp):
    ctx = _make_ctx(is_moderator=True)
    comp.bot.fetch_games = AsyncMock(return_value=[])
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("game", comp, ctx, new_game="不存在的分類")
    assert "找不到分類" in comp._ctx_reply.await_args[0][1]
    ctx.broadcaster.modify_channel.assert_not_called()


async def test_game_write_scope_error_triggers_reauth(comp):
    ctx = _make_ctx(is_moderator=True)
    comp.bot.fetch_games = AsyncMock(return_value=[MagicMock(id="1", name="G")])
    err = RuntimeError("Request failed with status 401: Missing scope: channel:manage:broadcast")
    err.status = 401
    ctx.broadcaster.modify_channel = AsyncMock(side_effect=err)
    comp._notify_reauth = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("game", comp, ctx, new_game="G")
    comp._notify_reauth.assert_awaited_once()


# --------------------------------------------------------------------------- #
# !tags — read
# --------------------------------------------------------------------------- #


async def test_tags_read_reports_current_tags(comp):
    ctx = _make_ctx()
    ctx.broadcaster.fetch_channel_info = AsyncMock(return_value=MagicMock(tags=["中文", "聊天"]))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("tags", comp, ctx)
    msg = comp._ctx_reply.await_args[0][1]
    assert "中文" in msg and "聊天" in msg


async def test_tags_read_reports_unset(comp):
    ctx = _make_ctx()
    ctx.broadcaster.fetch_channel_info = AsyncMock(return_value=MagicMock(tags=[]))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("tags", comp, ctx)
    assert "尚未設定" in comp._ctx_reply.await_args[0][1]


# --------------------------------------------------------------------------- #
# !tags <list> — write, moderator+ only
# --------------------------------------------------------------------------- #


async def test_tags_write_requires_moderator(comp):
    ctx = _make_ctx(is_moderator=False)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("tags", comp, ctx, new_tags="中文,聊天")
    assert "Mod" in comp._ctx_reply.await_args[0][1]
    ctx.broadcaster.modify_channel.assert_not_called()


async def test_tags_write_updates_as_moderator(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.modify_channel = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("tags", comp, ctx, new_tags=" 中文 , 聊天 ,New")
    ctx.broadcaster.modify_channel.assert_awaited_once_with(tags=["中文", "聊天", "New"])
    msg = comp._ctx_reply.await_args[0][1]
    assert "中文" in msg and "New" in msg
    comp.cmd_repo.increment_usage_count.assert_awaited_once_with("chan-1", "tags")


async def test_tags_write_rejects_too_many(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.modify_channel = AsyncMock()
    eleven = ",".join(f"t{i}" for i in range(11))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("tags", comp, ctx, new_tags=eleven)
    assert "最多只能設定 10 個標籤" in comp._ctx_reply.await_args[0][1]
    ctx.broadcaster.modify_channel.assert_not_called()


async def test_tags_write_rejects_too_long(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.modify_channel = AsyncMock()
    too_long = "a" * 26
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("tags", comp, ctx, new_tags=too_long)
    assert "標籤過長" in comp._ctx_reply.await_args[0][1]
    ctx.broadcaster.modify_channel.assert_not_called()


# --------------------------------------------------------------------------- #
# !marker — moderator+ only, no read side
# --------------------------------------------------------------------------- #


async def test_marker_creates_with_position(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.id = "chan-1"
    ctx.broadcaster.create_stream_marker = AsyncMock(return_value=MagicMock(position=754))
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("marker", comp, ctx, description="精彩片段")
    ctx.broadcaster.create_stream_marker.assert_awaited_once_with(
        token_for="chan-1", description="精彩片段"
    )
    assert "12:34" in comp._ctx_reply.await_args[0][1]
    comp.cmd_repo.increment_usage_count.assert_awaited_once_with("chan-1", "marker")


async def test_marker_truncates_long_description(comp):
    ctx = _make_ctx(is_moderator=True)
    ctx.broadcaster.id = "chan-1"
    ctx.broadcaster.create_stream_marker = AsyncMock(return_value=MagicMock(position=0))
    long_desc = "x" * 200
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("marker", comp, ctx, description=long_desc)
    _, kwargs = ctx.broadcaster.create_stream_marker.await_args
    assert len(kwargs["description"]) == 140


async def test_marker_scope_error_triggers_reauth(comp):
    ctx = _make_ctx(is_moderator=True)
    err = RuntimeError("Request failed with status 401: Missing scope: channel:manage:broadcast")
    err.status = 401
    ctx.broadcaster.create_stream_marker = AsyncMock(side_effect=err)
    comp._notify_reauth = AsyncMock()
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("marker", comp, ctx)
    comp._notify_reauth.assert_awaited_once()


async def test_marker_not_live_shows_friendly_message(comp):
    ctx = _make_ctx(is_moderator=True)
    err = RuntimeError("Request failed with status 400: stream not live")
    err.status = 400
    ctx.broadcaster.create_stream_marker = AsyncMock(side_effect=err)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call("marker", comp, ctx)
    assert "VOD" in comp._ctx_reply.await_args[0][1]
