"""Video Queue component: !vq, !np

Public (all users):
    !vq list        Show current + next 3 queued titles
    !vq remove      Remove caller's own most recent queued entry
    !np / !影片      Now playing: title, link, requester

Moderator+ only:
    !vq <URL>       Add a video to the queue (YouTube or Twitch Clip)
    !vq skip        Skip the current video
    !vq clear       Clear entire queue (current + all queued)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiohttp
from twitchio.ext import commands

from core.component import BotComponent
from core.config import get_settings
from shared.repositories.video_queue import (
    SOURCE_PRIORITY,
    VideoQueueBlocklistRepository,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    format_now_playing,
)
from shared.video_sources import (
    fetch_video_metadata,
    metadata_gate_unverifiable,
    resolve_video_url,
    unplayable_message,
)

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class VideoQueueComponent(BotComponent):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self._settings = get_settings()
        self.vq_repo = VideoQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_settings_repo = VideoQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_blocklist_repo = VideoQueueBlocklistRepository(self.bot.token_database)  # type: ignore[attr-defined]
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
        self.vq_blocklist_repo.pool = pool

    # ------------------------------------------------------------------
    # Shared: add video logic
    # ------------------------------------------------------------------

    async def _handle_add(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Core logic for adding a video to the queue."""
        try:
            await self._handle_add_inner(ctx, url_str)
        except Exception:
            LOGGER.exception(f"VideoQueue add failed for {url_str}")
            await self._ctx_reply(ctx, "目前暫時無法點播，請稍後再試 BloodTrail")

    async def _handle_add_inner(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Inner implementation — separated so exceptions surface as a reply."""
        channel_id = ctx.channel.id
        settings = await self.vq_settings_repo.get_or_create(channel_id)

        if not settings.enabled:
            await self._ctx_reply(ctx, "目前暫停開放影片點播")
            return

        # CLI add is restricted to moderators and broadcaster
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return  # silent

        user_name = ctx.chatter.display_name or ctx.chatter.name or ""
        user_id: str | None = ctx.chatter.id or None

        resolved = await resolve_video_url(url_str, session=self._session)
        if resolved is None:
            await self._ctx_reply(
                ctx, "這個連結無法使用，目前支援 YouTube / Twitch Clip / Bilibili"
            )
            return

        # Duplicate check
        if await self.vq_repo.video_is_active(channel_id, resolved.video_id):
            await self._ctx_reply(ctx, "這部影片已在待播中 KappaPride")
            return

        # Queue size check
        queue_size = await self.vq_repo.get_queue_size(channel_id)
        if queue_size >= settings.max_queue_size:
            await self._ctx_reply(
                ctx,
                f"目前待播已滿（{queue_size}/{settings.max_queue_size}），請稍後再試 ResidentSleeper",
            )
            return

        # Per-user active limit
        if settings.max_per_user > 0:
            active = await self.vq_repo.count_active_by_user(channel_id, user_name, user_id)
            if active >= settings.max_per_user:
                await self._ctx_reply(
                    ctx, f"你目前已達點播上限（{settings.max_per_user} 首） KappaPride"
                )
                return

        # User cooldown
        if settings.user_cooldown_seconds > 0:
            last = await self.vq_repo.find_last_entry_by_user(channel_id, user_name, user_id)
            if last and last.created_at:
                elapsed = (datetime.now(UTC) - last.created_at).total_seconds()
                if elapsed < settings.user_cooldown_seconds:
                    remaining = int(settings.user_cooldown_seconds - elapsed)
                    m, s = divmod(remaining, 60)
                    time_str = f"{m}:{s:02d}" if m > 0 else f"{s} 秒"
                    await self._ctx_reply(ctx, f"請於 {time_str} 後再點播 ResidentSleeper")
                    return

        metadata = await fetch_video_metadata(
            resolved,
            youtube_api_key=self._settings.youtube_api_key,
            twitch_client_id=self._settings.twitch_client_id,
            twitch_client_secret=self._settings.twitch_client_secret,
            session=self._session,
        )
        title, duration_seconds, view_count = (
            metadata.title,
            metadata.duration_seconds,
            metadata.view_count,
        )

        # Playability — an un-embeddable / age-restricted video only stalls the
        # overlay on its timer ceiling, so reject it up front.
        if not metadata.playable:
            await self._ctx_reply(ctx, unplayable_message(metadata.unplayable_reason))
            return

        # Minimum view count filter. A missing view_count from an authoritative
        # source is a transient failure (retry); a best-effort platform (Bilibili)
        # can never supply it, so the gate skips rather than blocking every add.
        if settings.min_view_count > 0:
            if metadata_gate_unverifiable(view_count, best_effort=metadata.metadata_best_effort):
                await self._ctx_reply(ctx, "目前無法確認影片資訊，請稍後再試 BloodTrail")
                return
            if view_count is not None and view_count < settings.min_view_count:
                await self._ctx_reply(
                    ctx, f"這部影片未達觀看數條件（需 {settings.min_view_count:,} 次以上）"
                )
                return

        # Global length cap — same best-effort handling as view count.
        if settings.max_duration_seconds:
            if metadata_gate_unverifiable(
                duration_seconds, best_effort=metadata.metadata_best_effort
            ):
                await self._ctx_reply(ctx, "目前無法確認影片資訊，請稍後再試 BloodTrail")
                return
            if duration_seconds is not None and duration_seconds > settings.max_duration_seconds:
                await self._ctx_reply(
                    ctx,
                    f"這部影片超過可點播的長度（上限 {settings.max_duration_seconds // 60} 分鐘）",
                )
                return

        # Replay cooldown — reject a video played again too soon
        if settings.replay_cooldown_hours and await self.vq_repo.played_within(
            channel_id, resolved.video_id, settings.replay_cooldown_hours
        ):
            await self._ctx_reply(
                ctx, f"這部影片在 {settings.replay_cooldown_hours} 小時內播過，請更換其他影片"
            )
            return

        # Blocklist — video / title keyword / requester
        blocked = await self.vq_blocklist_repo.check(
            channel_id,
            video_id=resolved.video_id,
            title=title,
            requested_by=user_name,
            requested_by_id=user_id,
        )
        if blocked is not None:
            await self._ctx_reply(ctx, "這部影片已被封鎖，無法點播 KappaPride")
            return

        entry = await self.vq_repo.add_if_within_limits(
            channel_id=channel_id,
            video_id=resolved.video_id,
            requested_by=user_name,
            source="chat",
            max_queue_size=settings.max_queue_size,
            max_per_user=settings.max_per_user,
            requested_by_id=user_id,
            title=title,
            duration_seconds=duration_seconds,
            is_vertical=metadata.is_vertical,
            thumbnail_url=metadata.thumbnail_url,
            video_type=resolved.video_type,
            priority=SOURCE_PRIORITY["chat"],
            start_seconds=resolved.start_seconds,
        )
        if entry is None:
            await self._ctx_reply(ctx, "點播失敗，請重新嘗試 BloodTrail")
            return
        position = await self.vq_repo.get_queue_size(channel_id)
        title_part = f"「{title}」" if title else ""
        dur_part = (
            f"({duration_seconds // 60}:{duration_seconds % 60:02d})" if duration_seconds else ""
        )
        info = f"{title_part}{dur_part}"
        await self._ctx_reply(
            ctx,
            f"{info + ' ' if info else ''}已加入待播（{position}/{settings.max_queue_size}） SeemsGood",
        )

    # ------------------------------------------------------------------
    # !np
    # ------------------------------------------------------------------

    @commands.command(name="np", aliases=["影片"])
    async def cmd_np(self, ctx: commands.Context[Bot]) -> None:
        """!np / !影片 — 顯示當前播放影片資訊"""
        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        if not current:
            await self._ctx_reply(ctx, "目前沒有播放中的影片")
            return

        await self._ctx_reply(ctx, format_now_playing(current))

    # ------------------------------------------------------------------
    # !vq — subcommand group
    # ------------------------------------------------------------------

    @commands.group(name="vq", invoke_fallback=True, case_insensitive=True)
    async def vq(self, ctx: commands.Context[Bot]) -> None:
        """!vq <URL> 投遞影片 | !vq list/remove/skip/clear 管理佇列"""
        if ctx.invoked_subcommand is not None:
            return
        args = (ctx.message.text if ctx.message else "").split(maxsplit=1)
        if len(args) > 1:
            await self._handle_add(ctx, args[1].strip())
        else:
            await self._ctx_reply(ctx, "用法：!vq <URL> | !vq list | !vq remove")

    @vq.command(name="skip")
    async def vq_skip(self, ctx: commands.Context[Bot]) -> None:
        """!vq skip — 跳過當前影片（moderator+）"""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        if not current:
            await self._ctx_reply(ctx, "目前沒有播放中的影片")
            return

        # Fetch next before atomic skip so we can include title in reply
        queued = await self.vq_repo.get_queued(channel_id)
        await self.vq_repo.skip_current_atomic(channel_id)
        if queued:
            next_title = queued[0].title or queued[0].video_id
            await self._ctx_reply(ctx, f"已跳過 › 下一首「{next_title}」")
        else:
            await self._ctx_reply(ctx, "已跳過，目前沒有其他待播影片 ResidentSleeper")

    @vq.command(name="clear")
    async def vq_clear(self, ctx: commands.Context[Bot]) -> None:
        """!vq clear — 清空整個佇列（moderator+）"""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        total = await self.vq_repo.clear_all_atomic(channel_id)
        await self._ctx_reply(ctx, f"已清空待播（{total} 首）")

    @vq.command(name="list")
    async def vq_list(self, ctx: commands.Context[Bot]) -> None:
        """!vq list — 顯示現正播放與待播前 3 首（標題，不含投遞者；查投遞者用 !np）"""
        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        queued = await self.vq_repo.get_queued(channel_id)

        if not current and not queued:
            await self._ctx_reply(ctx, "目前沒有待播影片")
            return

        parts: list[str] = []
        if current:
            parts.append(f"▶ {current.title or current.video_id}")
        if queued:
            titles = " ".join(f"{i}.{e.title or e.video_id}" for i, e in enumerate(queued[:3], 1))
            overflow = f"（+{len(queued) - 3} 首）" if len(queued) > 3 else ""
            parts.append(f"待播：{titles}{overflow}")
        await self._ctx_reply(ctx, " | ".join(parts))

    @vq.command(name="remove")
    async def vq_remove(self, ctx: commands.Context[Bot]) -> None:
        """!vq remove — 移除自己最後一首尚未播放的請求（所有人可用）"""
        channel_id = ctx.channel.id
        user_name = ctx.chatter.display_name or ctx.chatter.name or ""
        user_id: str | None = ctx.chatter.id or None
        entry = await self.vq_repo.find_last_queued_by_user(channel_id, user_name, user_id)
        if not entry:
            await self._ctx_reply(ctx, "你目前沒有待播影片")
            return
        await self.vq_repo.mark_skipped(entry.id, channel_id)
        await self._ctx_reply(ctx, f"已移除「{entry.title or entry.video_id}」")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(VideoQueueComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("VideoQueue component unloaded")
