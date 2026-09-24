"""Daily check-in chat command and development-only overlay trigger."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import twitchio.ext.commands as commands

from core.component import BotComponent
from core.config import get_settings
from core.guards import check_command
from shared.repositories.attendance import AttendanceRepository
from shared.repositories.command_config import CommandConfigRepository
from shared.repositories.community_overlay import CommunityOverlayRepository
from shared.services.attendance import AttendanceService
from shared.services.community_overlay import CommunityOverlayService

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

# 依語氣由輕到重排列，slot = min(int(rank / total * 5), 4)
_RANK_TEMPLATES = [
    "每當點名你都在！能在 {total} 人中排到【第 {rank} 名】，累積簽到 {days} 天，絕對是真愛 GivePLZ ",  # 前 20%
    "不是吧，這也能卷？在 {total} 人中你硬是衝到【第 {rank} 名】！累積簽到 {days} 天，我就問，你不用睡覺嗎？",  # 20–40%
    "這是真的嗎？從 {total} 人中殺出重圍奪下【第 {rank} 名】，累積簽到 {days} 天，你其實是機器人吧 MrDestructoid ",  # 40–60%
    "何意味？在 {total} 人中才排【第 {rank} 名】喔？才累積簽到 {days} 天，就繼續愛簽不簽吧，我沒關係啦真的😍",  # 60–80%
    "666 還有高手！你在 {total} 人中位居【第 {rank} 名】呢！累積簽到 {days} 天，這數據想低調都難 MingLee",  # 後 20%
]


class AttendanceComponent(BotComponent):
    """Channel-scoped community attendance commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        pool = self.bot.token_database  # type: ignore[attr-defined]
        self.cmd_repo = CommandConfigRepository(pool)
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self.attendance = AttendanceService(AttendanceRepository(pool))
        self.overlay = CommunityOverlayService(CommunityOverlayRepository(pool))
        self._is_development = get_settings().is_development

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool
        self.attendance.repository.pool = pool
        self.overlay.repository.pool = pool

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        try:
            channel_id = ctx.channel.id
            await self.cmd_repo.increment_usage_count(channel_id, command_name)
            session_id = self.bot.sessions.session_id(channel_id)
            if session_id:
                await self.bot.analytics.record_command_usage(
                    session_id=session_id,
                    channel_id=channel_id,
                    command_name=f"!{command_name}",
                )
        except Exception:
            LOGGER.exception("Failed to record %s command usage", command_name)

    @commands.command(name="checkin", aliases=["簽到"])
    async def checkin(self, ctx: commands.Context) -> None:
        """Record one daily check-in for this channel."""
        config = await check_command(
            self.cmd_repo,
            ctx,
            command_name="checkin",
            channel_repo=self.channel_repo,
        )
        if not config:
            return

        channel_id = ctx.channel.id
        username = ctx.chatter.name or str(ctx.chatter.id)
        display_name = ctx.chatter.display_name or None
        session_id = self.bot.sessions.session_id(channel_id) or None
        try:
            outcome = await self.attendance.check_in_with_reply(
                channel_id=channel_id,
                user_id=str(ctx.chatter.id),
                username=username,
                display_name=display_name,
                session_id=session_id,
            )
        except Exception:
            LOGGER.exception(
                "Check-in failed",
                extra={"channel_id": channel_id, "user_id": str(ctx.chatter.id)},
            )
            await self._ctx_reply(ctx, "簽到失敗，請稍後再試")
            return

        if outcome.delay_seconds > 0:
            await asyncio.sleep(outcome.delay_seconds)
        await self._ctx_reply(ctx, outcome.message)
        await self._record_command(ctx, "checkin")

    @commands.command(aliases=["排名"])
    async def rank(self, ctx: commands.Context) -> None:
        """查詢累積簽到排名。

        Usage: !rank, !排名
        """
        config = await check_command(
            self.cmd_repo, ctx, command_name="rank", channel_repo=self.channel_repo
        )
        if not config:
            return

        channel_id = ctx.channel.id
        user_id = str(ctx.chatter.id)
        try:
            data = await self.attendance.get_rank(channel_id, user_id)
        except Exception:
            LOGGER.exception(
                "Rank lookup failed", extra={"channel_id": channel_id, "user_id": user_id}
            )
            await self._ctx_reply(ctx, "排名查詢失敗，請稍後再試")
            return

        if data is None:
            await self._ctx_reply(ctx, "還沒有簽到紀錄，先去簽到再來看排名吧")
            await self._record_command(ctx, "rank")
            return

        slot = min(int(data.rank / data.total_participants * 5), 4)
        template = _RANK_TEMPLATES[slot]
        await self._ctx_reply(
            ctx,
            template.format(rank=data.rank, total=data.total_participants, days=data.total_days),
        )
        await self._record_command(ctx, "rank")

    @commands.command(name="ovltest")
    async def ovltest(self, ctx: commands.Context, count: int = 7) -> None:
        """Publish a preview event in development without changing check-in data."""
        if not self._is_development or str(ctx.chatter.id) != str(ctx.channel.id):
            return
        if not 1 <= count <= 9999:
            await self._ctx_reply(ctx, "用法：!ovltest [1-9999]")
            return

        try:
            await self.overlay.publish_checkin_preview(
                channel_id=ctx.channel.id,
                actor_user_id=str(ctx.chatter.id),
                actor_display_name=ctx.chatter.display_name or ctx.chatter.name or "Streamer",
                total_days=count,
            )
        except Exception:
            LOGGER.exception("Development overlay preview publish failed")
            await self._ctx_reply(ctx, "OVL 測試事件送出失敗")
            return

        await self._ctx_reply(ctx, f"OVL 測試事件已送出：第 {count} 天")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(AttendanceComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
