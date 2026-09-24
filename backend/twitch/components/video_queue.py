"""Video Queue component: !vq, !np

Public (all users):
    !vq list        Show current + next 3 queued titles
    !vq remove      Remove caller's own most recent queued entry
    !np / !影片      Now playing: title, link, requester

Moderator+ only:
    !vq <URL>       Add a video (YouTube, Twitch Clip/VOD, Instagram Reel, Bilibili)
    !vq skip        Skip the current video
    !vq clear       Clear entire queue (current + all queued)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
import twitchio.ext.commands as commands

from core.component import BotComponent
from core.config import get_settings
from shared.repositories.video_queue import (
    VideoQueueBlocklistRepository,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    format_now_playing,
)
from shared.services.video_queue_admission import (
    AdmissionReason,
    AdmissionRejected,
    VideoQueueAdmissionService,
)
from shared.video_sources import (
    fetch_video_metadata,
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
            # Do not copy a submitted URL into logs: query strings may contain
            # short-lived tokens or other user-provided data.
            LOGGER.exception("VideoQueue add failed", extra={"channel_id": ctx.channel.id})
            await self._ctx_reply(ctx, "目前暫時無法點播，請稍後再試 BloodTrail")

    async def _handle_add_inner(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Inner implementation — separated so exceptions surface as a reply."""
        channel_id = ctx.channel.id

        # CLI add is restricted to moderators and broadcaster
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return  # silent

        user_name = ctx.chatter.display_name or ctx.chatter.name or ""
        user_id: str | None = ctx.chatter.id or None
        admission = VideoQueueAdmissionService(
            self.vq_repo, self.vq_settings_repo, self.vq_blocklist_repo
        )
        try:
            result = await admission.admit(
                channel_id=channel_id,
                url=url_str,
                requested_by=user_name,
                requested_by_id=user_id,
                source="chat",
                resolve=lambda url: resolve_video_url(url, session=self._session),
                fetch_metadata=lambda resolved: fetch_video_metadata(
                    resolved,
                    youtube_api_key=self._settings.youtube_api_key,
                    twitch_client_id=self._settings.twitch_client_id,
                    twitch_client_secret=self._settings.twitch_client_secret,
                    instafix_host=self._settings.instafix_host,
                    session=self._session,
                ),
            )
        except AdmissionRejected as error:
            reason = error.reason
            details = error.details
            if reason is AdmissionReason.DISABLED:
                message = "目前暫停開放影片點播"
            elif reason is AdmissionReason.INVALID_URL:
                message = (
                    "這個連結無法使用，目前支援 YouTube、Twitch Clip/VOD、Bilibili、Instagram Reel"
                )
            elif reason is AdmissionReason.DUPLICATE:
                message = "這部影片已在待播中 KappaPride"
            elif reason is AdmissionReason.QUEUE_FULL:
                message = (
                    f"目前待播已滿（{details['queue_size']}/{details['max_queue_size']}），"
                    "請稍後再試 ResidentSleeper"
                )
            elif reason is AdmissionReason.USER_LIMIT:
                message = f"你目前已達點播上限（{details['max_per_user']} 首） KappaPride"
            elif reason is AdmissionReason.USER_COOLDOWN:
                remaining = int(details["remaining_seconds"])
                minutes, seconds = divmod(remaining, 60)
                time_text = f"{minutes}:{seconds:02d}" if minutes else f"{seconds} 秒"
                message = f"請於 {time_text} 後再點播 ResidentSleeper"
            elif reason is AdmissionReason.NOT_PLAYABLE:
                message = unplayable_message(str(details.get("unplayable_reason") or ""))
            elif reason is AdmissionReason.METADATA_UNVERIFIABLE:
                message = "目前無法確認影片資訊，請稍後再試 BloodTrail"
            elif reason is AdmissionReason.MIN_VIEWS:
                message = f"這部影片未達觀看數條件（需 {details['min_view_count']:,} 次以上）"
            elif reason is AdmissionReason.TOO_LONG:
                message = (
                    f"這部影片超過可點播的長度（上限 {int(details['limit_seconds']) // 60} 分鐘）"
                )
            elif reason is AdmissionReason.REPLAY_COOLDOWN:
                message = f"這部影片在 {details['hours']} 小時內播過，請更換其他影片"
            elif reason is AdmissionReason.BLOCKED:
                message = "這部影片已被封鎖，無法點播 KappaPride"
            else:
                message = "點播失敗，請重新嘗試 BloodTrail"
            await self._ctx_reply(ctx, message)
            return

        title = result.metadata.title
        duration_seconds = result.metadata.duration_seconds
        title_part = f"「{title}」" if title else ""
        dur_part = (
            f"({duration_seconds // 60}:{duration_seconds % 60:02d})" if duration_seconds else ""
        )
        info = f"{title_part}{dur_part}"
        await self._ctx_reply(
            ctx,
            f"{info + ' ' if info else ''}已加入待播（{result.position}/{result.settings.max_queue_size}） SeemsGood",
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
