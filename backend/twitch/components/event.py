import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from shared.repositories.event_config import DEFAULT_TEMPLATES, EventConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot


LOGGER: logging.Logger = logging.getLogger("EventComponent")


class EventComponent(commands.Component):
    """EventSub 事件監聽組件"""

    # 防刷機制設定
    COOLDOWN_HOURS = 24  # 冷卻時間（小時）
    CACHE_CLEANUP_INTERVAL = 100  # 每處理 N 個事件就清理一次過期 cache

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        # 追隨事件 cache: {user_id: last_notified_time}
        self._follow_cache: dict[str, datetime] = {}
        # 事件計數器，用於定期清理
        self._event_counter = 0
        # Event config repository (with TTL cache)
        self.event_configs = EventConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]

    def _cleanup_cache(self, cache: dict[str, datetime]) -> None:
        """清理過期的 cache 項目"""
        now = datetime.now()
        cooldown = timedelta(hours=self.COOLDOWN_HOURS)
        expired_keys = [
            user_id for user_id, last_time in cache.items() if now - last_time > cooldown
        ]
        for key in expired_keys:
            del cache[key]
        if expired_keys:
            LOGGER.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def _should_notify(self, user_id: str) -> bool:
        """檢查是否應該發送通知（防刷機制，僅用於追隨事件）"""
        self._event_counter += 1

        # 定期清理過期 cache
        if self._event_counter % self.CACHE_CLEANUP_INTERVAL == 0:
            self._cleanup_cache(self._follow_cache)

        now = datetime.now()
        cooldown = timedelta(hours=self.COOLDOWN_HOURS)

        if user_id in self._follow_cache:
            last_time = self._follow_cache[user_id]
            time_diff = now - last_time
            if time_diff < cooldown:
                return False

        # 更新 cache
        self._follow_cache[user_id] = now
        return True

    async def _get_message(
        self, channel_id: str, event_type: str, variables: dict[str, str]
    ) -> str | None:
        """Fetch template from DB and resolve variables. Returns None if disabled."""
        config = await self.event_configs.get_config(channel_id, event_type)
        if config is None:
            # No config yet — use hardcoded default
            template = DEFAULT_TEMPLATES.get(event_type)
            if template is None:
                return None
        else:
            if not config.enabled:
                return None
            template = config.message_template

        message = template
        for key, value in variables.items():
            message = message.replace(f"$({key})", value)
        return message

    @commands.Component.listener()
    async def event_follow(
        self,
        payload: twitchio.ChannelFollow,
    ) -> None:
        """追隨事件"""
        user_name = payload.user.display_name or payload.user.name or ""
        user_id = payload.user.id
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id

        # 防刷檢查
        if not self._should_notify(user_id):
            LOGGER.info(f"[{broadcaster_name}] Follow: {user_name} (cooldown)")
            return

        try:
            message = await self._get_message(channel_id, "follow", {"user": user_name})
            if message is None:
                LOGGER.info(f"[{broadcaster_name}] Follow: {user_name} (disabled)")
                return

            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[{broadcaster_name}] Follow: {user_name}")

            # Record to analytics database
            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    analytics = self.bot.analytics
                    await analytics.record_follow_event(
                        session_id=session_id,
                        channel_id=channel_id,
                        user_id=user_id,
                        username=payload.user.name or user_name,
                        display_name=payload.user.display_name,
                        occurred_at=datetime.now(),
                    )
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] Follow: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_subscription(
        self,
        payload: twitchio.ChannelSubscribe,
    ) -> None:
        """訂閱事件"""
        user_name = payload.user.display_name or payload.user.name or ""
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id
        tier_name = {
            "1000": "T1",
            "2000": "T2",
            "3000": "T3",
        }.get(payload.tier, payload.tier)

        sub_type = "Gift" if payload.gift else "Sub"

        try:
            message = await self._get_message(
                channel_id, "subscribe", {"user": user_name, "tier": tier_name}
            )
            if message is None:
                LOGGER.info(
                    f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name}) (disabled)"
                )
                return

            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name})")

            # Record to analytics database
            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    analytics = self.bot.analytics
                    await analytics.record_subscribe_event(
                        session_id=session_id,
                        channel_id=channel_id,
                        user_id=payload.user.id,
                        username=payload.user.name or user_name,
                        display_name=payload.user.display_name,
                        tier=payload.tier,
                        is_gift=payload.gift,
                        occurred_at=datetime.now(),
                    )
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name}) (error: {e})")

    @commands.Component.listener()
    async def event_raid(
        self,
        payload: twitchio.ChannelRaid,
    ) -> None:
        """Raid 事件 - 自動 shoutout raider 頻道"""
        raider_name = payload.from_broadcaster.display_name or payload.from_broadcaster.name or ""
        raider_id = payload.from_broadcaster.id
        broadcaster_name = payload.to_broadcaster.name
        broadcaster_id = payload.to_broadcaster.id
        viewer_count = payload.viewer_count

        try:
            # 取得 config 以判斷 auto_shoutout 選項
            config = await self.event_configs.get_config(broadcaster_id, "raid")
            auto_shoutout = True
            if config is not None:
                auto_shoutout = config.options.get("auto_shoutout", True)

            # 發送感謝訊息（可被 disabled）
            message = await self._get_message(
                broadcaster_id, "raid", {"user": raider_name, "count": str(viewer_count)}
            )
            if message is not None:
                await payload.to_broadcaster.send_message(
                    message=message,
                    sender=self.bot.bot_id,
                    token_for=self.bot.bot_id,
                )

            # 執行 Shoutout（依據 config options 控制）
            if auto_shoutout:
                await self.bot._http.post_chat_shoutout(
                    broadcaster_id=broadcaster_id,
                    to_broadcaster_id=raider_id,
                    moderator_id=self.bot.bot_id,
                    token_for=broadcaster_id,
                )
            LOGGER.info(
                f"[{broadcaster_name}] Raid: {raider_name} ({viewer_count})"
                f" - Shoutout {'sent' if auto_shoutout else 'skipped'}"
            )

        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] Raid: {raider_name} (error: {e})")


async def setup(bot: commands.Bot) -> None:
    component = EventComponent(bot)
    await bot.add_component(component)
    LOGGER.info("EventComponent loaded with listeners: event_follow, event_subscribe, event_raid")


async def teardown(bot: commands.Bot) -> None: ...
