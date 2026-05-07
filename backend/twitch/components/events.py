import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from shared.repositories.event_config import DEFAULT_TEMPLATES, EventConfigRepository
from utils.reauth import is_scope_error, reauth_notifier

if TYPE_CHECKING:
    from core.bot import Bot


LOGGER: logging.Logger = logging.getLogger(__name__)

_TIER_MAP = {"1000": "T1", "2000": "T2", "3000": "T3"}


class EventComponent(commands.Component):
    """EventSub 事件監聽組件"""

    COOLDOWN_HOURS = 24
    CACHE_CLEANUP_INTERVAL = 100

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self._follow_cache: dict[str, datetime] = {}
        self._event_counter = 0
        # Event config repository (with TTL cache)
        self.event_configs = EventConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]

    def refresh_pool(self, pool) -> None:
        self.event_configs.pool = pool

    def _cleanup_cache(self, cache: dict[str, datetime]) -> None:
        """清理過期的 cache 項目"""
        now = datetime.now(UTC)
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

        if self._event_counter % self.CACHE_CLEANUP_INTERVAL == 0:
            self._cleanup_cache(self._follow_cache)

        now = datetime.now(UTC)
        cooldown = timedelta(hours=self.COOLDOWN_HOURS)

        if user_id in self._follow_cache:
            last_time = self._follow_cache[user_id]
            time_diff = now - last_time
            if time_diff < cooldown:
                return False

        self._follow_cache[user_id] = now
        return True

    async def _get_message(
        self, channel_id: str, event_type: str, variables: dict[str, str]
    ) -> str | None:
        """Fetch template from DB and resolve variables. Returns None if disabled."""
        try:
            config = await self.event_configs.get_config(channel_id, event_type)
        except Exception as e:
            LOGGER.warning(
                f"DB unavailable for event config ({event_type}), using default template: {e}"
            )
            config = None
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
        """追隨事件

        NOTE: always-on — fires via EventSub regardless of streaming state.
        Analytics recording is the only part gated behind an active session.
        """
        user_name = payload.user.display_name or payload.user.name or ""
        user_id = payload.user.id
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id

        # Always persist follow_since (idempotent COALESCE upsert)
        if hasattr(self.bot, "analytics"):
            try:
                followed_at = getattr(payload, "followed_at", None) or datetime.now(UTC)
                await self.bot.analytics.upsert_viewer_follow_status(
                    channel_id=channel_id,
                    user_id=user_id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    follow_since=followed_at,
                )
            except Exception as e:
                LOGGER.warning(f"[{broadcaster_name}] Follow status upsert failed: {e}")

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
            )
            LOGGER.info(f"[{broadcaster_name}] Follow: {user_name}")

            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    await self.bot.analytics.record_follow_event(
                        session_id=session_id,
                        channel_id=channel_id,
                        user_id=user_id,
                        username=payload.user.name or user_name,
                        display_name=payload.user.display_name,
                        occurred_at=datetime.now(UTC),
                    )
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] Follow: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_subscription(
        self,
        payload: twitchio.ChannelSubscribe,
    ) -> None:
        """訂閱事件

        NOTE: always-on — fires via EventSub regardless of streaming state.
        Analytics recording is the only part gated behind an active session.
        """
        user_name = payload.user.display_name or payload.user.name or ""
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id
        tier_name = _TIER_MAP.get(payload.tier, payload.tier)

        sub_type = "Gift" if payload.gift else "Sub"

        # Always persist subscription status regardless of notification config
        if hasattr(self.bot, "analytics"):
            try:
                await self.bot.analytics.upsert_viewer_subscription(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    sub_tier=tier_name,
                    sub_gifted=bool(payload.gift),
                )
            except Exception as e:
                LOGGER.warning(f"[{broadcaster_name}] Subscription status upsert failed: {e}")

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
            )
            LOGGER.info(f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name})")

            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    await self.bot.analytics.record_subscribe_event(
                        session_id=session_id,
                        channel_id=channel_id,
                        user_id=payload.user.id,
                        username=payload.user.name or user_name,
                        display_name=payload.user.display_name,
                        tier=payload.tier,
                        is_gift=payload.gift,
                        occurred_at=datetime.now(UTC),
                    )
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name}) (error: {e})")

    @commands.Component.listener()
    async def event_subscription_gift(
        self,
        payload: twitchio.ChannelSubscriptionGift,
    ) -> None:
        """贈禮訂閱事件 — 更新贈禮者累計數量。

        cumulative_total 是 Twitch 提供的該用戶在此頻道的歷史累計贈禮數，
        與單次批次數量無關，直接 upsert 即可保持最新值。
        Anonymous gifts carry no user, so we skip them.
        """
        if payload.anonymous or not payload.user:
            return

        channel_id = payload.broadcaster.id
        broadcaster_name = payload.broadcaster.name
        cumulative = getattr(payload, "cumulative_total", None)
        if cumulative is None:
            return

        if hasattr(self.bot, "analytics"):
            try:
                await self.bot.analytics.upsert_viewer_gift_count(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or "",
                    display_name=payload.user.display_name,
                    total_gifts_given=int(cumulative),
                )
            except Exception as e:
                LOGGER.warning(f"[{broadcaster_name}] Gift upsert failed: {e}")

    @commands.Component.listener()
    async def event_cheer(
        self,
        payload: twitchio.ChannelCheer,
    ) -> None:
        """Bits (Cheer) 事件

        NOTE: always-on — fires via EventSub regardless of streaming state.
        """
        if payload.anonymous:
            user_name = "匿名用戶"
        else:
            user_name = (
                (payload.user.display_name or payload.user.name or "")
                if payload.user
                else "匿名用戶"
            )
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id
        bits_amount = payload.bits

        try:
            message = await self._get_message(
                channel_id, "bits", {"user": user_name, "amount": str(bits_amount)}
            )
            if message is None:
                LOGGER.info(
                    f"[{broadcaster_name}] Cheer: {user_name} {bits_amount} bits (disabled)"
                )
                return

            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
            )
            LOGGER.info(f"[{broadcaster_name}] Cheer: {user_name} {bits_amount} bits")

            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    user_id = (
                        None if payload.anonymous else (payload.user.id if payload.user else None)
                    )
                    await self.bot.analytics.record_cheer_event(
                        session_id=session_id,
                        channel_id=channel_id,
                        user_id=user_id,
                        username=payload.user.name
                        if payload.user and not payload.anonymous
                        else user_name,
                        bits=bits_amount,
                        occurred_at=datetime.now(UTC),
                    )

        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] Cheer: {user_name} {bits_amount} bits (error: {e})")

    @commands.Component.listener()
    async def event_raid(
        self,
        payload: twitchio.ChannelRaid,
    ) -> None:
        """Raid 事件 - 自動 shoutout raider 頻道

        NOTE: always-on — fires via EventSub regardless of streaming state.
        """
        raider_name = payload.from_broadcaster.display_name or payload.from_broadcaster.name or ""
        raider_id = payload.from_broadcaster.id
        broadcaster_name = payload.to_broadcaster.name
        broadcaster_id = payload.to_broadcaster.id
        viewer_count = payload.viewer_count

        try:
            config = await self.event_configs.get_config(broadcaster_id, "raid")
            auto_shoutout = True
            if config is not None:
                auto_shoutout = config.options.get("auto_shoutout", True)

            message = await self._get_message(
                broadcaster_id, "raid", {"user": raider_name, "count": str(viewer_count)}
            )
            if message is not None:
                await payload.to_broadcaster.send_message(
                    message=message,
                    sender=self.bot.bot_id,
                )

            shoutout_sent = False
            if auto_shoutout:
                try:
                    await self.bot._http.post_chat_shoutout(
                        broadcaster_id=broadcaster_id,
                        to_broadcaster_id=raider_id,
                        moderator_id=self.bot.bot_id,
                        token_for=self.bot.bot_id,
                    )
                    shoutout_sent = True
                except Exception as shoutout_err:
                    if is_scope_error(shoutout_err):
                        await reauth_notifier.notify(
                            broadcaster_login=broadcaster_name or "",
                            channel_id=broadcaster_id,
                            send_fn=lambda msg: payload.to_broadcaster.send_message(
                                message=msg,
                                sender=self.bot.bot_id,
                            ),
                        )
                    else:
                        LOGGER.error(f"[{broadcaster_name}] Shoutout failed: {shoutout_err}")

            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(broadcaster_id)
                if session_id:
                    await self.bot.analytics.record_raid_event(
                        session_id=session_id,
                        channel_id=broadcaster_id,
                        from_broadcaster_id=raider_id,
                        from_broadcaster_name=payload.from_broadcaster.name or raider_name,
                        viewers=viewer_count,
                        occurred_at=datetime.now(UTC),
                    )

            LOGGER.info(
                f"[{broadcaster_name}] Raid: {raider_name} ({viewer_count})"
                f" (shoutout {'sent' if shoutout_sent else 'skipped'})"
            )

        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] Raid: {raider_name} (error: {e})")

    @commands.Component.listener()
    async def event_subscription_end(
        self,
        payload: twitchio.ChannelSubscriptionEnd,
    ) -> None:
        """訂閱到期事件"""
        channel_id = payload.broadcaster.id
        broadcaster_name = payload.broadcaster.name
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                await self.bot.analytics.upsert_viewer_subscription_end(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                )
            LOGGER.info(f"[{broadcaster_name}] SubEnd: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{broadcaster_name}] SubEnd: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_moderator_add(
        self,
        payload: twitchio.ChannelModeratorAdd,
    ) -> None:
        """頻道新增管理員"""
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                await self.bot.analytics.upsert_viewer_mod_status(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    is_mod=True,
                )
            LOGGER.info(f"[{payload.broadcaster.name}] ModAdd: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] ModAdd: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_moderator_remove(
        self,
        payload: twitchio.ChannelModeratorRemove,
    ) -> None:
        """頻道移除管理員"""
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                await self.bot.analytics.upsert_viewer_mod_status(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    is_mod=False,
                )
            LOGGER.info(f"[{payload.broadcaster.name}] ModRemove: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] ModRemove: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_vip_add(
        self,
        payload: twitchio.ChannelVIPAdd,
    ) -> None:
        """頻道新增 VIP"""
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                await self.bot.analytics.upsert_viewer_vip_status(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    is_vip=True,
                )
            LOGGER.info(f"[{payload.broadcaster.name}] VIPAdd: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] VIPAdd: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_vip_remove(
        self,
        payload: twitchio.ChannelVIPRemove,
    ) -> None:
        """頻道移除 VIP"""
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                await self.bot.analytics.upsert_viewer_vip_status(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    is_vip=False,
                )
            LOGGER.info(f"[{payload.broadcaster.name}] VIPRemove: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] VIPRemove: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_ban(
        self,
        payload: twitchio.ChannelBan,
    ) -> None:
        """封禁事件"""
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                ends_at: datetime | None = getattr(payload, "ends_at", None)
                reason: str | None = getattr(payload, "reason", None) or None
                await self.bot.analytics.upsert_viewer_ban(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    ban_expires_at=ends_at,
                    ban_reason=reason,
                )
            LOGGER.info(f"[{payload.broadcaster.name}] Ban: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] Ban: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_unban(
        self,
        payload: twitchio.ChannelUnban,
    ) -> None:
        """解除封禁事件"""
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            if hasattr(self.bot, "analytics"):
                await self.bot.analytics.upsert_viewer_unban(
                    channel_id=channel_id,
                    user_id=payload.user.id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                )
            LOGGER.info(f"[{payload.broadcaster.name}] Unban: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] Unban: {user_name} (error: {e})")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(EventComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
