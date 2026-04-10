"""Video Queue component: !vq, !np

Public (all users):
    !vq list        Show first 5 videos in queue
    !np             Now playing: title, link, remaining time, queue info

Moderator+ only:
    !vq <URL>       Add a video to the queue (YouTube or Twitch Clip)
    !vq remove      Remove the most recent queued entry submitted by the caller
    !vq skip        Skip the current video
    !vq clear       Clear entire queue (current + all queued)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiohttp
from twitchio.ext import commands

from core.config import get_settings
from shared.repositories.video_queue import (
    SOURCE_PRIORITY,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    extract_twitch_clip_slug,
    extract_youtube_info,
    fetch_twitch_clip_info,
    fetch_yt_info,
)

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER = logging.getLogger(__name__)


class VideoQueueComponent(commands.Component):
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

    def refresh_pool(self, pool) -> None:
        self.vq_repo.pool = pool
        self.vq_settings_repo.pool = pool

    # ------------------------------------------------------------------
    # Shared: add video logic
    # ------------------------------------------------------------------

    async def _handle_add(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Core logic for adding a video to the queue."""
        try:
            await self._handle_add_inner(ctx, url_str)
        except Exception:
            LOGGER.exception("_handle_add failed for %s", url_str)
            await ctx.reply("點歌失敗，請稍後再試")

    async def _handle_add_inner(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Inner implementation — separated so exceptions surface as a reply."""
        channel_id = ctx.channel.id
        settings = await self.vq_settings_repo.get_or_create(channel_id)

        if not settings.enabled:
            await ctx.reply("影片佇列目前已關閉")
            return

        # CLI add is restricted to moderators and broadcaster
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return  # silent

        user_name = ctx.chatter.name or ctx.chatter.display_name or ""

        # Detect URL type: try YouTube first, then Twitch clip
        video_id, is_vertical = extract_youtube_info(url_str)
        clip_slug: str | None = None
        if not video_id:
            clip_slug = extract_twitch_clip_slug(url_str)
            if not clip_slug:
                await ctx.reply("請提供有效的 YouTube 或 Twitch Clip 連結")
                return

        # Exactly one of clip_slug or video_id is non-None here (the early return above ensures this).
        active_id: str = clip_slug if clip_slug else video_id  # type: ignore[assignment]

        # Duplicate check
        if await self.vq_repo.video_is_active(channel_id, active_id):
            await ctx.reply("該影片已在佇列中")
            return

        # Queue size check
        queue_size = await self.vq_repo.get_queue_size(channel_id)
        if queue_size >= settings.max_queue_size:
            await ctx.reply(f"佇列已滿（{queue_size}/{settings.max_queue_size}）")
            return

        # Per-user active limit
        if settings.max_per_user > 0:
            active = await self.vq_repo.count_active_by_user(channel_id, user_name)
            if active >= settings.max_per_user:
                await ctx.reply(f"每人上限 {settings.max_per_user} 首，請等待您的影片播放後再點歌")
                return

        # User cooldown
        if settings.user_cooldown_seconds > 0:
            last = await self.vq_repo.find_last_entry_by_user(channel_id, user_name)
            if last and last.created_at:
                elapsed = (datetime.now(UTC) - last.created_at).total_seconds()
                if elapsed < settings.user_cooldown_seconds:
                    remaining = int(settings.user_cooldown_seconds - elapsed)
                    m, s = divmod(remaining, 60)
                    time_str = f"{m}:{s:02d}" if m > 0 else f"{s} 秒"
                    await ctx.reply(f"點歌冷卻中，請等待 {time_str}")
                    return

        if clip_slug:
            # Fetch Twitch clip metadata
            title, duration_seconds, view_count = await fetch_twitch_clip_info(
                clip_slug, self._settings.client_id, self._settings.client_secret, self._session
            )
            video_id = clip_slug
            is_vertical = False
            video_type = "twitch_clip"
        else:
            assert video_id is not None  # guaranteed: clip_slug is None only when video_id is set
            # Fetch info from YouTube Data API (graceful fallback on failure)
            title, duration_seconds, view_count, is_vertical_from_api = await fetch_yt_info(
                video_id, self._settings.youtube_api_key, self._session
            )
            is_vertical = is_vertical or is_vertical_from_api
            video_type = "youtube"

        # Minimum view count filter
        if settings.min_view_count > 0:
            if view_count is None:
                await ctx.reply("無法驗證影片資訊，請稍後再試")
                return
            if view_count < settings.min_view_count:
                await ctx.reply(
                    f"影片觀看次數不足（{view_count:,} 次 < {settings.min_view_count:,} 次），無法加入佇列"
                )
                return

        await self.vq_repo.add(
            channel_id=channel_id,
            video_id=video_id,
            requested_by=user_name,
            source="chat",
            title=title,
            duration_seconds=duration_seconds,
            is_vertical=is_vertical,
            video_type=video_type,
            priority=SOURCE_PRIORITY["chat"],
        )
        position = await self.vq_repo.get_queue_size(channel_id)
        title_part = f"「{title}」" if title else ""
        dur_part = (
            f"({duration_seconds // 60}:{duration_seconds % 60:02d})" if duration_seconds else ""
        )
        info = " ".join(filter(None, [title_part, dur_part]))
        await ctx.reply(
            f"{info + ' ' if info else ''}已加入佇列！（{position}/{settings.max_queue_size}）"
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

        url = (
            f"https://clips.twitch.tv/{current.video_id}"
            if current.video_type == "twitch_clip"
            else f"https://youtu.be/{current.video_id}"
        )
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

    @commands.group(name="vq", invoke_fallback=True)
    async def vq(self, ctx: commands.Context[Bot]) -> None:
        """!vq <URL> 投遞影片 | !vq list/remove/skip/clear 管理佇列"""
        if ctx.invoked_subcommand is not None:
            return
        args = (ctx.message.text if ctx.message else "").split(maxsplit=1)
        if len(args) > 1:
            await self._handle_add(ctx, args[1].strip())
        else:
            await ctx.reply("📹 !vq <URL> 投遞影片 | !vq list 顯示佇列 | !vq remove 移除請求")

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

        await self.vq_repo.mark_skipped(current.id, channel_id)
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
            await self.vq_repo.mark_skipped(current.id, channel_id)
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
        """!vq remove — 移除最後一首尚未播放的請求（moderator+）"""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return
        channel_id = ctx.channel.id
        user_name = ctx.chatter.name or ctx.chatter.display_name or ""
        entry = await self.vq_repo.find_last_queued_by_user(channel_id, user_name)
        if not entry:
            await ctx.reply("沒有可移除的請求")
            return
        await self.vq_repo.mark_skipped(entry.id, channel_id)
        await ctx.reply(f"已移除「{entry.title or entry.video_id}」")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(VideoQueueComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("VideoQueue component unloaded")
