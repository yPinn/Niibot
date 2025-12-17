import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

if TYPE_CHECKING:
    pass
else:
    pass


LOGGER: logging.Logger = logging.getLogger("EventComponent")


class EventComponent(commands.Component):
    """EventSub 事件監聽組件"""

    # 防刷機制設定
    COOLDOWN_HOURS = 24  # 冷卻時間（小時）
    CACHE_CLEANUP_INTERVAL = 100  # 每處理 N 個事件就清理一次過期 cache

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # 追隨事件 cache: {user_id: last_notified_time}
        self._follow_cache: dict[str, datetime] = {}
        # 事件計數器，用於定期清理
        self._event_counter = 0

    def _cleanup_cache(self, cache: dict[str, datetime]) -> None:
        """清理過期的 cache 項目"""
        now = datetime.now()
        cooldown = timedelta(hours=self.COOLDOWN_HOURS)
        expired_keys = [
            user_id
            for user_id, last_time in cache.items()
            if now - last_time > cooldown
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

    @commands.Component.listener()
    async def event_follow(
        self,
        payload: twitchio.ChannelFollow,
    ) -> None:
        """追隨事件"""
        user_name = payload.user.display_name or payload.user.name
        user_id = payload.user.id
        broadcaster_name = payload.broadcaster.name

        # 防刷檢查
        if not self._should_notify(user_id):
            LOGGER.info(f"[{broadcaster_name}] Follow: {user_name} (cooldown)")
            return

        try:
            message = f"感謝 {user_name} 的追隨！"
            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[{broadcaster_name}] Follow: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] Follow: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_subscribe(
        self,
        payload: twitchio.ChannelSubscribe,
    ) -> None:
        """訂閱事件"""
        user_name = payload.user.display_name or payload.user.name
        broadcaster_name = payload.broadcaster.name
        tier_name = {
            "1000": "T1",
            "2000": "T2",
            "3000": "T3",
        }.get(payload.tier, payload.tier)

        sub_type = "Gift" if payload.gift else "Sub"

        try:
            message = f"感謝 {user_name} 的訂閱！"

            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name})")
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name}) (error: {e})")


async def setup(bot: commands.Bot) -> None:
    component = EventComponent(bot)
    await bot.add_component(component)
    LOGGER.info("EventComponent loaded with listeners: event_follow, event_subscribe")


async def teardown(bot: commands.Bot) -> None:
    ...
