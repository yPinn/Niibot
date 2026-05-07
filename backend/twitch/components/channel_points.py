import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiohttp
import asyncpg
import twitchio
from twitchio.ext import commands

from core.config import get_settings
from shared.repositories.command_config import RedemptionConfigRepository
from shared.repositories.game_queue import GameQueueRepository, GameQueueSettingsRepository
from shared.repositories.video_queue import (
    SOURCE_PRIORITY,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    extract_bilibili_bvid,
    extract_twitch_clip_slug,
    extract_youtube_info,
    fetch_bilibili_info,
    fetch_twitch_clip_info,
    fetch_yt_info,
)
from utils.reauth import is_scope_error, reauth_notifier

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger(__name__)


class ChannelPointsComponent(commands.Component):
    """Channel Points 兌換監聽組件"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.settings = get_settings()
        self.redemption_repo = RedemptionConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.gq_repo = GameQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.gq_settings_repo = GameQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_repo = VideoQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_settings_repo = VideoQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self._session: aiohttp.ClientSession | None = None

    def refresh_pool(self, pool) -> None:
        self.redemption_repo.pool = pool
        self.gq_repo.pool = pool
        self.gq_settings_repo.pool = pool
        self.vq_repo.pool = pool
        self.vq_settings_repo.pool = pool

    async def component_load(self) -> None:
        self._session = aiohttp.ClientSession()

    async def component_teardown(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def _reply(self, broadcaster: twitchio.PartialUser, message: str) -> None:
        """Send a bot message to a channel."""
        await broadcaster.send_message(
            message=message,
            sender=self.bot.bot_id,
        )

    @commands.Component.listener()
    async def event_custom_redemption_add(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """Channel Points 兌換事件"""
        LOGGER.debug(f"event_custom_redemption_add triggered: {type(payload).__name__}")

        channel_name = payload.broadcaster.name
        user_name = payload.user.display_name or payload.user.name
        reward_title = payload.reward.title
        reward_cost = payload.reward.cost
        user_input = payload.user_input or ""

        LOGGER.info(f"[{channel_name}] {user_name} redeemed '{reward_title}' ({reward_cost} pts)")
        if user_input:
            LOGGER.debug(f"[{channel_name}] User input: {user_input}")

        await self._handle_redemption(payload)

    async def _handle_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """處理兌換事件（DB 驅動比對）"""
        reward_title = payload.reward.title
        user_name = payload.user.display_name or payload.user.name
        channel_id = payload.broadcaster.id

        channel_name = payload.broadcaster.name

        config = await self.redemption_repo.find_by_reward_name(channel_id, reward_title)
        if not config:
            LOGGER.debug(f"[{channel_name}] No matching redemption config for: {reward_title}")
            return

        if config.action_type == "niibot_auth" and user_name:
            owner_id = self.settings.owner_id
            if channel_id == owner_id:
                await self._handle_niibot_redemption(payload, user_name)
            else:
                LOGGER.warning(
                    f"[{channel_name}] {user_name} attempted niibot_auth on non-owner channel"
                )
        elif config.action_type == "first" and user_name:
            await self._handle_first_redemption(payload, user_name)
        elif config.action_type == "vip":
            await self._handle_vip_redemption(payload, user_name)
        elif config.action_type == "game_queue" and user_name:
            await self._handle_game_queue_redemption(payload, user_name)
        elif config.action_type == "video_queue" and user_name:
            await self._handle_video_queue_redemption(payload, user_name)

    async def _handle_vip_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str | None,
    ) -> None:
        """處理 VIP 獎勵兌換"""
        channel_name = payload.broadcaster.name
        broadcaster = payload.broadcaster
        try:
            await broadcaster.add_vip(user=payload.user)
            try:
                await self._reply(broadcaster, f"@{user_name} 恭喜你成為尊榮的 VIP 大人！")
                LOGGER.info(f"[{channel_name}] VIP granted to {user_name}")
            except Exception as e:
                LOGGER.warning(f"[{channel_name}] VIP granted but failed to send message: {e}")

        except Exception as e:
            if is_scope_error(e):
                await reauth_notifier.notify(
                    broadcaster_login=channel_name or "",
                    channel_id=str(broadcaster.id),
                    send_fn=lambda msg: self._reply(broadcaster, msg),
                )
                return

            status = getattr(e, "status", None) or getattr(e, "status_code", None)
            body = str(e).lower()
            if status == 422:
                if "moderator" in body:
                    LOGGER.warning(
                        f"[{channel_name}] {user_name} is already a moderator, cannot grant VIP"
                    )
                    error_message = f"@{user_name} 你已經是 Moderator 了！"
                elif "already a vip" in body:
                    LOGGER.info(f"[{channel_name}] {user_name} is already a VIP")
                    error_message = f"@{user_name} 你已經是 VIP 了！"
                else:
                    LOGGER.error(f"[{channel_name}] Failed to grant VIP (422): {e}")
                    error_message = f"@{user_name} VIP 授予失敗，請聯繫管理員！"
            else:
                LOGGER.error(f"[{channel_name}] Failed to grant VIP: {e}")
                error_message = f"@{user_name} VIP 授予失敗，請聯繫管理員！"

            try:
                await self._reply(broadcaster, error_message)
            except Exception:
                pass

    async def _handle_first_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理搶第一遊戲兌換"""
        channel_name = payload.broadcaster.name
        broadcaster = payload.broadcaster
        try:
            try:
                await broadcaster.send_announcement(
                    message=f"@{user_name} 恭喜你搶到沙發！",
                    moderator=self.bot.bot_id,
                    color="primary",
                )
                LOGGER.info(f"[{channel_name}] First claimed by {user_name}")
            except Exception as e:
                LOGGER.error(f"[{channel_name}] First announcement failed, falling back: {e}")
                try:
                    await self._reply(broadcaster, f"@{user_name} 恭喜你搶到第一！")
                    LOGGER.info(f"[{channel_name}] First fallback message sent to {user_name}")
                except Exception as fallback_error:
                    LOGGER.error(f"[{channel_name}] First fallback also failed: {fallback_error}")

        except Exception as e:
            LOGGER.error(f"[{channel_name}] First claim error: {e}")

    async def _handle_niibot_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理 Niibot 獎勵兌換"""
        channel_name = payload.broadcaster.name
        broadcaster = payload.broadcaster
        try:
            oauth_url = self.settings.frontend_url
            try:
                await self._reply(broadcaster, f"@{user_name} 已將授權連結發送至你的 Twitch 私訊！")
                LOGGER.info(f"[{channel_name}] Niibot auth: confirmation sent to {user_name}")
            except Exception as e:
                LOGGER.warning(f"[{channel_name}] Niibot auth: failed to send public message: {e}")

            whisper_message = f"請點擊以下連結，授權 Niibot 存取你的頻道： {oauth_url}"
            try:
                bot_user = self.bot.create_partialuser(user_id=self.bot.bot_id)
                await bot_user.send_whisper(
                    to_user=payload.user,
                    message=whisper_message,
                )
                LOGGER.info(f"[{channel_name}] Niibot auth: whisper sent to {user_name}")
            except Exception as e:
                LOGGER.error(f"[{channel_name}] Niibot auth: failed to send whisper: {e}")
                if is_scope_error(e):
                    await reauth_notifier.notify(
                        broadcaster_login=channel_name or "",
                        channel_id=str(broadcaster.id),
                        send_fn=lambda msg: self._reply(broadcaster, msg),
                    )
                try:
                    await self._reply(
                        broadcaster,
                        f"@{user_name} 私訊發送失敗，請聯繫 @llazypilot 獲取授權連結！",
                    )
                    LOGGER.error(
                        f"[{channel_name}] Niibot auth: whisper failed, fell back to chat message"
                    )
                except Exception as fallback_error:
                    LOGGER.error(
                        f"[{channel_name}] Niibot auth: fallback also failed: {fallback_error}"
                    )

        except Exception as e:
            LOGGER.error(f"[{channel_name}] Niibot auth error: {e}")

    async def _handle_game_queue_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理遊戲排隊兌換"""
        broadcaster = payload.broadcaster
        channel_id = broadcaster.id
        user_id = payload.user.id

        try:
            settings = await self.gq_settings_repo.get_or_create(channel_id)
            if not settings.enabled:
                await self._reply(broadcaster, f"@{user_name} 隊列未開放")
                return

            existing = await self.gq_repo.find_active_by_user(channel_id, user_id)
            if existing:
                entries = await self.gq_repo.get_active_entries(channel_id)
                position = next((i + 1 for i, e in enumerate(entries) if e.user_id == user_id), 0)
                await self._reply(broadcaster, f"@{user_name} 已在隊列中，第{position}位")
                return

            try:
                await self.gq_repo.add_entry(channel_id, user_id, user_name)
            except asyncpg.UniqueViolationError:
                LOGGER.debug(
                    f"[{broadcaster.name}] GameQueue: duplicate entry race for {user_name}"
                )
                return

            position = await self.gq_repo.count_active(channel_id)
            await self._reply(broadcaster, f"@{user_name} 已加入隊列，第{position}位")
            LOGGER.info(f"[{broadcaster.name}] GameQueue: {user_name} joined (position {position})")

        except Exception as e:
            if is_scope_error(e):
                await reauth_notifier.notify(
                    broadcaster_login=broadcaster.name or "",
                    channel_id=str(broadcaster.id),
                    send_fn=lambda msg: self._reply(broadcaster, msg),
                )
                return
            LOGGER.error(f"[{broadcaster.name}] GameQueue error: {e}")

    async def _handle_video_queue_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理影片佇列點數兌換（無 role 檢查：已兌換點數視為授權）"""
        broadcaster = payload.broadcaster
        channel_id = broadcaster.id
        user_input = payload.user_input or ""
        user_id: str | None = payload.user.id or None

        try:
            settings = await self.vq_settings_repo.get_or_create(channel_id)
            if not settings.enabled or not settings.redemption_enabled:
                await self._reply(broadcaster, f"@{user_name} 影片佇列目前已關閉")
                return

            video_id, is_vertical = extract_youtube_info(user_input)
            clip_slug: str | None = None
            bvid: str | None = None
            if not video_id:
                clip_slug = extract_twitch_clip_slug(user_input)
            if not video_id and not clip_slug:
                bvid = extract_bilibili_bvid(user_input)
            if not video_id and not clip_slug and not bvid:
                await self._reply(
                    broadcaster,
                    f"@{user_name} 請在兌換時輸入有效的 YouTube、Twitch Clip 或 Bilibili 連結",
                )
                return

            active_id: str = clip_slug or bvid or video_id  # type: ignore[assignment]

            if await self.vq_repo.video_is_active(channel_id, active_id):
                await self._reply(broadcaster, f"@{user_name} 該影片已在佇列中")
                return

            queue_size = await self.vq_repo.get_queue_size(channel_id)
            if queue_size >= settings.max_queue_size:
                await self._reply(
                    broadcaster,
                    f"@{user_name} 佇列已滿（{queue_size}/{settings.max_queue_size}）",
                )
                return

            if settings.max_per_user > 0:
                active = await self.vq_repo.count_active_by_user(channel_id, user_name, user_id)
                if active >= settings.max_per_user:
                    await self._reply(
                        broadcaster,
                        f"@{user_name} 每人上限 {settings.max_per_user} 首，請等待您的影片播放後再點歌",
                    )
                    return

            if settings.user_cooldown_seconds > 0:
                last = await self.vq_repo.find_last_entry_by_user(channel_id, user_name, user_id)
                if last and last.created_at:
                    elapsed = (datetime.now(UTC) - last.created_at).total_seconds()
                    if elapsed < settings.user_cooldown_seconds:
                        remaining = int(settings.user_cooldown_seconds - elapsed)
                        m, s = divmod(remaining, 60)
                        time_str = f"{m}:{s:02d}" if m > 0 else f"{s} 秒"
                        await self._reply(
                            broadcaster, f"@{user_name} 點歌冷卻中，請等待 {time_str}"
                        )
                        return

            if clip_slug:
                title, duration_seconds, view_count = await fetch_twitch_clip_info(
                    clip_slug,
                    self.settings.twitch_client_id,
                    self.settings.twitch_client_secret,
                    self._session,
                )
                video_id = clip_slug
                is_vertical = False
                video_type = "twitch_clip"
            elif bvid:
                title, duration_seconds, view_count, is_vertical = await fetch_bilibili_info(
                    bvid, self._session
                )
                video_id = bvid
                video_type = "bilibili"
            else:
                assert video_id is not None
                title, duration_seconds, view_count, is_vertical_from_api = await fetch_yt_info(
                    video_id,
                    self.settings.youtube_api_key,
                    self._session,
                )
                is_vertical = is_vertical or is_vertical_from_api
                video_type = "youtube"

            # View count check — if threshold is set and API failed to return view_count,
            # reject rather than silently bypassing the filter.
            if settings.min_view_count > 0:
                if view_count is None:
                    await self._reply(broadcaster, f"@{user_name} 無法驗證影片資訊，請稍後再試")
                    return
                if view_count < settings.min_view_count:
                    await self._reply(
                        broadcaster,
                        (
                            f"@{user_name} 影片觀看次數不足（{view_count:,} 次 < "
                            f"{settings.min_view_count:,} 次），無法加入佇列"
                        ),
                    )
                    return

            if duration_seconds and duration_seconds > settings.max_duration_redemption:
                max_m, max_s = divmod(settings.max_duration_redemption, 60)
                vid_m, vid_s = divmod(duration_seconds, 60)
                await self._reply(
                    broadcaster,
                    f"@{user_name} 影片長度 {vid_m}:{vid_s:02d} 超過上限 {max_m}:{max_s:02d}",
                )
                return

            await self.vq_repo.add(
                channel_id=channel_id,
                video_id=video_id,  # type: ignore[arg-type]
                requested_by=user_name,
                source="redemption",
                title=title,
                duration_seconds=duration_seconds,
                is_vertical=is_vertical,
                video_type=video_type,
                priority=SOURCE_PRIORITY["redemption"],
                requested_by_id=user_id,
            )
            position = await self.vq_repo.get_queue_size(channel_id)
            title_part = f"「{title}」" if title else ""
            dur_part = (
                f"({duration_seconds // 60}:{duration_seconds % 60:02d})"
                if duration_seconds
                else ""
            )
            info = " ".join(filter(None, [title_part, dur_part]))
            await self._reply(
                broadcaster,
                f"@{user_name} {info + ' ' if info else ''}已加入影片佇列！({position}/{settings.max_queue_size})",
            )

        except Exception as e:
            if is_scope_error(e):
                await reauth_notifier.notify(
                    broadcaster_login=broadcaster.name or "",
                    channel_id=str(broadcaster.id),
                    send_fn=lambda msg: self._reply(broadcaster, msg),
                )
                return
            LOGGER.error(f"[{broadcaster.name}] VideoQueue error: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(ChannelPointsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
