"""Video Queue component: !sr, !np, !vq

Public:
    !sr <URL>       Request a YouTube video
    !np             Now playing: title, link, remaining time, queue info

Moderator+:
    !vq skip        Skip the current video
    !vq clear       Clear entire queue (current + all queued)
    !vq list        Show first 5 videos in queue

Anyone:
    !vq remove      Remove your last queued (not yet playing) request
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiohttp
from twitchio.ext import commands

from core.config import get_settings
from core.guards import has_role
from shared.repositories.video_queue import (
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    extract_youtube_id,
    fetch_yt_info,
)

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER = logging.getLogger("VideoQueue")


class VideoQueueManagerComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self._settings = get_settings()
        self.vq_repo = VideoQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_settings_repo = VideoQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self._session: aiohttp.ClientSession | None = None

    async def component_load(self) -> None:
        self._session = aiohttp.ClientSession()
        LOGGER.info("VideoQueue component loaded")

    async def component_teardown(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # !sr <URL>
    # ------------------------------------------------------------------

    @commands.command(name="sr")
    async def cmd_sr(self, ctx: commands.Context[Bot]) -> None:
        """!sr <YouTube URL> — 投遞影片至佇列"""
        channel_id = ctx.channel.id
        settings = await self.vq_settings_repo.get_or_create(channel_id)

        if not settings.enabled:
            await ctx.reply("影片佇列目前已關閉")
            return

        if not has_role(ctx.chatter, settings.min_role_chat):
            return  # silent — consistent with game_queue

        args = (ctx.message.text if ctx.message else "").split(maxsplit=1)
        url_str = args[1].strip() if len(args) > 1 else ""
        video_id = extract_youtube_id(url_str)
        if not video_id:
            await ctx.reply("請提供有效的 YouTube 連結，例如：!sr https://youtu.be/dQw4w9WgXcQ")
            return

        # Duplicate check
        if await self.vq_repo.video_is_active(channel_id, video_id):
            await ctx.reply(f"@{ctx.chatter.display_name} 該影片已在佇列中")
            return

        # Queue size check
        queue_size = await self.vq_repo.get_queue_size(channel_id)
        if queue_size >= settings.max_queue_size:
            await ctx.reply(
                f"@{ctx.chatter.display_name} 佇列已滿（{queue_size}/{settings.max_queue_size}）"
            )
            return

        # Fetch info from YouTube Data API (graceful fallback on failure)
        title, duration_seconds = await fetch_yt_info(
            video_id, self._settings.youtube_api_key, self._session
        )

        # Duration validation (only when API returned a value)
        if duration_seconds and duration_seconds > settings.max_duration_seconds:
            max_m, max_s = divmod(settings.max_duration_seconds, 60)
            vid_m, vid_s = divmod(duration_seconds, 60)
            await ctx.reply(
                f"@{ctx.chatter.display_name} "
                f"影片長度 {vid_m}:{vid_s:02d} 超過上限 {max_m}:{max_s:02d}"
            )
            return

        await self.vq_repo.add(
            channel_id=channel_id,
            video_id=video_id,
            requested_by=ctx.chatter.display_name or ctx.chatter.name or "",
            source="chat",
            title=title,
            duration_seconds=duration_seconds,
        )
        position = queue_size + 1
        title_display = f"「{title}」" if title else ""
        await ctx.reply(
            f"@{ctx.chatter.display_name} {title_display}已加入佇列！"
            f"({position}/{settings.max_queue_size})"
        )

    # ------------------------------------------------------------------
    # !np
    # ------------------------------------------------------------------

    @commands.command(name="np")
    async def cmd_np(self, ctx: commands.Context[Bot]) -> None:
        """!np — 顯示當前影片、剩餘時間及待播資訊"""
        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        if not current:
            await ctx.reply("目前沒有正在播放的影片")
            return

        url = f"https://youtu.be/{current.video_id}"
        title_part = f"「{current.title}」 " if current.title else ""

        remaining_str = ""
        if current.started_at and current.duration_seconds:
            elapsed = (datetime.now(UTC) - current.started_at).total_seconds()
            remaining = max(0, current.duration_seconds - int(elapsed))
            m, s = divmod(remaining, 60)
            remaining_str = f" | 剩餘 {m}:{s:02d}"

        queued = await self.vq_repo.get_queued(channel_id)
        queue_str = ""
        if queued:
            total_dur = sum(e.duration_seconds or 0 for e in queued)
            if total_dur > 0:
                tm, ts = divmod(total_dur, 60)
                queue_str = f" | 待播 {len(queued)} 部（共 {tm}:{ts:02d}）"
            else:
                queue_str = f" | 待播 {len(queued)} 部"

        await ctx.reply(
            f"▶ {title_part}{url}{remaining_str}{queue_str} (由 {current.requested_by} 投遞)"
        )

    # ------------------------------------------------------------------
    # !vq — subcommand group
    # ------------------------------------------------------------------

    @commands.group(name="vq")
    async def vq(self, ctx: commands.Context[Bot]) -> None:
        """!vq — 影片佇列管理"""
        if ctx.invoked_subcommand is not None:
            return
        await ctx.reply("用法: !vq skip | !vq clear | !vq list | !vq remove")

    @vq.command(name="skip")
    async def vq_skip(self, ctx: commands.Context[Bot]) -> None:
        """!vq skip — 跳過當前影片（moderator+）"""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        if not current:
            await ctx.reply("目前沒有正在播放的影片")
            return

        await self.vq_repo.mark_skipped(current.id)
        queued = await self.vq_repo.get_queued(channel_id)
        if queued:
            await self.vq_repo.set_playing(queued[0].id)
            next_title = queued[0].title or queued[0].video_id
            await ctx.reply(f"已跳過，下一首：「{next_title}」")
        else:
            await ctx.reply("已跳過，佇列已空")

    @vq.command(name="clear")
    async def vq_clear(self, ctx: commands.Context[Bot]) -> None:
        """!vq clear — 清空整個佇列（moderator+）"""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        if current:
            await self.vq_repo.mark_skipped(current.id)
        count = await self.vq_repo.clear_queued(channel_id)
        total = count + (1 if current else 0)
        await ctx.reply(f"已清空佇列（共 {total} 首）")

    @vq.command(name="list")
    async def vq_list(self, ctx: commands.Context[Bot]) -> None:
        """!vq list — 顯示佇列前 5 首"""
        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        queued = await self.vq_repo.get_queued(channel_id)

        if not current and not queued:
            await ctx.reply("佇列目前是空的")
            return

        parts: list[str] = []
        if current:
            parts.append(f"▶ {current.title or current.video_id} ({current.requested_by})")
        for i, e in enumerate(queued[:4], 1):
            parts.append(f"{i}. {e.title or e.video_id} ({e.requested_by})")
        if len(queued) > 4:
            parts.append(f"...還有 {len(queued) - 4} 首")
        await ctx.reply(" | ".join(parts))

    @vq.command(name="remove")
    async def vq_remove(self, ctx: commands.Context[Bot]) -> None:
        """!vq remove — 移除自己最後一首尚未播放的請求"""
        channel_id = ctx.channel.id
        user_name = ctx.chatter.display_name or ctx.chatter.name or ""
        entry = await self.vq_repo.find_last_queued_by_user(channel_id, user_name)
        if not entry:
            await ctx.reply(f"@{user_name} 沒有可移除的請求")
            return
        await self.vq_repo.mark_skipped(entry.id)
        await ctx.reply(f"@{user_name} 已移除「{entry.title or entry.video_id}」")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(VideoQueueManagerComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("VideoQueue component unloaded")
