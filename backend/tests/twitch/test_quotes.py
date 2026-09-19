"""Unit tests for twitch.components.quotes — !quote / !quote add / !quote del.

Invoke the raw command callback via `.callback(component, ctx, args=...)` to
bypass the TwitchIO Command descriptor. `check_command` and `quote_repo` are
mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.quotes import QuoteComponent

from shared.models.quote import Quote

pytestmark = pytest.mark.asyncio

PATCH_CHECK = "twitch.components.quotes.check_command"

_QUOTE = Quote(
    id=1,
    channel_id="chan-1",
    quote_number=3,
    quote_text="這波不虧",
    created_by="streamer",
    created_at=datetime.now(UTC),
)


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
    ctx.chatter.display_name = "Streamer"
    ctx.chatter.name = "streamer"
    ctx.channel.id = "chan-1"
    ctx.channel.name = "streamer"
    return ctx


@pytest.fixture()
def comp() -> QuoteComponent:
    c = QuoteComponent(_make_bot())
    c._ctx_reply = AsyncMock()
    c.cmd_repo.increment_usage_count = AsyncMock()
    c.quote_repo = MagicMock()
    c.quote_repo.add = AsyncMock()
    c.quote_repo.get_random = AsyncMock()
    c.quote_repo.get_by_number = AsyncMock()
    c.quote_repo.delete = AsyncMock()
    return c


async def _call(comp: QuoteComponent, ctx: MagicMock, args: str | None = None) -> None:
    await QuoteComponent.quote.callback(comp, ctx, args=args)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# read
# --------------------------------------------------------------------------- #


async def test_disabled_command_is_silent(comp):
    ctx = _make_ctx()
    with patch(PATCH_CHECK, AsyncMock(return_value=None)):
        await _call(comp, ctx)
    comp._ctx_reply.assert_not_called()
    comp.quote_repo.get_random.assert_not_called()


async def test_no_args_shows_random_quote(comp):
    ctx = _make_ctx()
    comp.quote_repo.get_random.return_value = _QUOTE
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx)
    comp.quote_repo.get_random.assert_awaited_once_with("chan-1")
    msg = comp._ctx_reply.await_args[0][1]
    assert "#3" in msg and "這波不虧" in msg


async def test_no_quotes_yet(comp):
    ctx = _make_ctx()
    comp.quote_repo.get_random.return_value = None
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx)
    assert "還沒有語錄" in comp._ctx_reply.await_args[0][1]


async def test_numeric_arg_looks_up_by_number(comp):
    ctx = _make_ctx()
    comp.quote_repo.get_by_number.return_value = _QUOTE
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="3")
    comp.quote_repo.get_by_number.assert_awaited_once_with("chan-1", 3)
    comp.quote_repo.get_random.assert_not_called()


async def test_lookup_failure_is_generic(comp):
    ctx = _make_ctx()
    comp.quote_repo.get_random.side_effect = RuntimeError("boom")
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx)
    assert "查詢失敗" in comp._ctx_reply.await_args[0][1]


# --------------------------------------------------------------------------- #
# add — moderator+ only
# --------------------------------------------------------------------------- #


async def test_add_requires_moderator(comp):
    ctx = _make_ctx(is_moderator=False)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="add 新語錄")
    assert "Mod" in comp._ctx_reply.await_args[0][1]
    comp.quote_repo.add.assert_not_called()


async def test_add_creates_quote_as_moderator(comp):
    ctx = _make_ctx(is_moderator=True)
    comp.quote_repo.add.return_value = _QUOTE
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="add 這波不虧")
    comp.quote_repo.add.assert_awaited_once_with("chan-1", "這波不虧", "Streamer")
    assert "#3" in comp._ctx_reply.await_args[0][1]
    comp.cmd_repo.increment_usage_count.assert_awaited_once_with("chan-1", "quote")


async def test_add_rejects_empty_body(comp):
    ctx = _make_ctx(is_moderator=True)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="add   ")
    assert "用法" in comp._ctx_reply.await_args[0][1]
    comp.quote_repo.add.assert_not_called()


async def test_add_rejects_too_long(comp):
    ctx = _make_ctx(is_moderator=True)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="add " + "x" * 451)
    assert "過長" in comp._ctx_reply.await_args[0][1]
    comp.quote_repo.add.assert_not_called()


# --------------------------------------------------------------------------- #
# del — moderator+ only
# --------------------------------------------------------------------------- #


async def test_del_requires_moderator(comp):
    ctx = _make_ctx(is_moderator=False)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="del 3")
    assert "Mod" in comp._ctx_reply.await_args[0][1]
    comp.quote_repo.delete.assert_not_called()


async def test_del_removes_quote_as_moderator(comp):
    ctx = _make_ctx(is_moderator=True)
    comp.quote_repo.delete.return_value = True
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="del 3")
    comp.quote_repo.delete.assert_awaited_once_with("chan-1", 3)
    assert "已刪除語錄 #3" in comp._ctx_reply.await_args[0][1]


async def test_del_not_found(comp):
    ctx = _make_ctx(is_moderator=True)
    comp.quote_repo.delete.return_value = False
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="del 999")
    assert "找不到語錄 #999" in comp._ctx_reply.await_args[0][1]


async def test_del_rejects_non_numeric(comp):
    ctx = _make_ctx(is_moderator=True)
    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _call(comp, ctx, args="del abc")
    assert "用法" in comp._ctx_reply.await_args[0][1]
    comp.quote_repo.delete.assert_not_called()
