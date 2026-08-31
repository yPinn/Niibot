"""Twitch Tarot command integration with Live Display events."""

from __future__ import annotations

import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from twitch.components.tarot import TarotComponent, format_tarot_reply  # noqa: E402

PATCH_CHECK = "twitch.components.tarot.check_command"


def _component() -> TarotComponent:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    component = TarotComponent(bot)
    component._ctx_reply = AsyncMock()
    component.overlay = MagicMock()
    component.overlay.publish_tarot = AsyncMock(return_value=93)
    component.cmd_repo.increment_usage_count = AsyncMock()
    component._get_daily_card = MagicMock(return_value=("0", False))
    return component


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = "ch1"
    ctx.chatter.id = "u1"
    ctx.chatter.name = "alice"
    ctx.chatter.display_name = "Alice"
    return ctx


async def _tarot(component: TarotComponent, ctx: MagicMock, args: str | None = None) -> None:
    await TarotComponent.tarot.callback(component, ctx, args=args)  # type: ignore[attr-defined]


def test_tarot_reply_formatter_preserves_details_within_twitch_limit() -> None:
    reply = format_tarot_reply(
        category_label="感情",
        card_name="測試牌",
        orientation="正位",
        keywords="・".join(["關鍵字"] * 40),
        meaning="牌義" * 300,
        advice="可執行建議" * 100,
    )

    assert len(reply) <= 500
    assert reply.startswith("🃏 感情｜測試牌（正位）")
    assert "解讀：" in reply
    assert "今日建議：" in reply


@pytest.mark.asyncio
async def test_command_replies_and_publishes_complete_tarot_overlay_event() -> None:
    component = _component()
    ctx = _ctx()

    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _tarot(component, ctx, "感情")

    component._ctx_reply.assert_awaited_once()
    component._get_daily_card.assert_called_once_with("u1", "love")
    reply = component._ctx_reply.await_args.args[1]
    card = component.tarot_data["cards"]["0"]
    assert card["upright"]["meanings"]["love"].replace("\n", "") in reply
    assert card["upright"]["advice"].replace("\n", "") in reply
    assert reply.startswith("🃏 感情｜")
    assert "今日建議" in reply
    assert len(reply) <= 500
    kwargs = component.overlay.publish_tarot.await_args.kwargs
    assert kwargs["channel_id"] == "ch1"
    assert kwargs["actor_user_id"] == "u1"
    assert kwargs["actor_display_name"] == "Alice"
    assert kwargs["payload"]["card_id"] == "0"
    assert kwargs["payload"]["category"] == "love"
    assert kwargs["payload"]["image_path"].endswith("/major-00-the-fool.jpg")


@pytest.mark.asyncio
async def test_unknown_topic_replies_with_recovery_without_drawing() -> None:
    component = _component()
    ctx = _ctx()

    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _tarot(component, ctx, "健康")

    reply = component._ctx_reply.await_args.args[1]
    assert "找不到「健康」這個主題" in reply
    assert "綜合、感情、事業、財運" in reply
    assert "!塔羅 感情" in reply
    component._get_daily_card.assert_not_called()
    component.overlay.publish_tarot.assert_not_awaited()
    component.cmd_repo.increment_usage_count.assert_not_awaited()


@pytest.mark.asyncio
async def test_overlay_failure_does_not_suppress_tarot_chat_reply() -> None:
    component = _component()
    component.overlay.publish_tarot.side_effect = RuntimeError("overlay unavailable")
    ctx = _ctx()

    with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
        await _tarot(component, ctx)

    component._ctx_reply.assert_awaited_once()
    component.cmd_repo.increment_usage_count.assert_awaited_once_with("ch1", "tarot")
