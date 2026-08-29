import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from shared.events import tier_label
from utils.event_render import clean_message_var, render_template
from utils.reauth import is_scope_error, reauth_notifier

if TYPE_CHECKING:
    from core.bot import Bot


LOGGER: logging.Logger = logging.getLogger(__name__)


class EventComponent(commands.Component):
    """EventSub 事件監聽組件"""

    COOLDOWN_HOURS = 24
    CACHE_CLEANUP_INTERVAL = 100

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self._follow_cache: dict[str, datetime] = {}
        self._event_counter = 0
        # Shared with the bot, which seeds defaults on subscribe; one TTL cache.
        self.event_configs = self.bot.event_configs  # type: ignore[attr-defined]

    def _trigger_emote_sync(self, channel_id: str) -> None:
        """Fire emote sync as a background task when bot mod status changes."""
        import asyncio

        for comp in self.bot._components.values():
            if hasattr(comp, "sync_emotes"):
                task = asyncio.create_task(comp.sync_emotes(channel_id))
                self.bot._background_tasks.add(task)
                task.add_done_callback(self.bot._background_tasks.discard)
                return

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

    def _bot_has_mod(self, channel_id: str) -> bool:
        return channel_id in self.bot._bot_is_mod  # type: ignore[attr-defined]

    def _session_id(self, channel_id: str) -> int | None:
        """Active stream-session id for this channel, or None when not live.

        Stream-event analytics (``record_*_event``) only makes sense during a
        session; viewer-state upserts run regardless.
        """
        return self.bot.sessions.session_id(channel_id)

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

    async def _get_template(self, channel_id: str, event_type: str) -> str | None:
        """The channel's message template for an event, or None to stay silent.

        Fails closed: a missing config row (channel never seeded / opened the
        dashboard), a disabled event, or a DB read error all mean "don't post".
        The bot seeds event_configs on subscribe, so a missing row is rare.
        """
        try:
            config = await self.event_configs.get_config(channel_id, event_type)
        except Exception as e:
            LOGGER.warning(f"[{channel_id}] event config read failed ({event_type}), silent: {e}")
            return None
        if config is None or not config.enabled:
            return None
        return config.message_template

    async def _notify(
        self, channel_id: str, event_type: str, variables: dict[str, str], *, label: str
    ) -> bool:
        """Post the channel's configured greeting for an event.

        Returns True if a message was sent. Silent (False) when the bot is not
        a mod in the channel, the event is disabled / unconfigured, or the send
        fails — every reason is logged against *label*.
        """
        if not self._bot_has_mod(channel_id):
            LOGGER.debug(f"{label} (bot not mod, skipped)")
            return False

        template = await self._get_template(channel_id, event_type)
        if template is None:
            LOGGER.info(f"{label} (disabled)")
            return False

        try:
            await self.bot.create_partialuser(channel_id).send_message(
                message=render_template(template, variables),
                sender=self.bot.bot_id,
            )
        except Exception as e:
            LOGGER.error(f"{label} (error: {e})")
            return False

        LOGGER.info(label)
        return True

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

        # Always persist follow_since (idempotent COALESCE upsert), even when
        # the greeting is disabled / the bot is not a mod.
        try:
            await self.bot.analytics.upsert_viewer_follow_status(
                channel_id=channel_id,
                user_id=user_id,
                username=payload.user.name or user_name,
                display_name=payload.user.display_name,
                follow_since=payload.followed_at,
            )
        except Exception as e:
            LOGGER.warning(f"[{broadcaster_name}] Follow status upsert failed: {e}")

        if not self._should_notify(user_id):
            LOGGER.info(f"[{broadcaster_name}] Follow: {user_name} (cooldown)")
            return

        label = f"[{broadcaster_name}] Follow: {user_name}"
        if not await self._notify(channel_id, "follow", {"user": user_name}, label=label):
            return

        try:
            session_id = self._session_id(channel_id)
            if session_id is not None:
                await self.bot.analytics.record_follow_event(
                    session_id=session_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    username=payload.user.name or user_name,
                    display_name=payload.user.display_name,
                    occurred_at=datetime.now(UTC),
                )
        except Exception as e:
            LOGGER.warning(f"[{broadcaster_name}] Follow analytics failed: {e}")

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
        tier_name = tier_label(payload.tier)

        sub_type = "Gift" if payload.gift else "Sub"

        # Always persist subscription status regardless of notification config
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

        label = f"[{broadcaster_name}] {sub_type}: {user_name} ({tier_name})"
        if not await self._notify(
            channel_id, "subscribe", {"user": user_name, "tier": tier_name}, label=label
        ):
            return

        try:
            session_id = self._session_id(channel_id)
            if session_id is not None:
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
            LOGGER.warning(f"[{broadcaster_name}] {sub_type} analytics failed: {e}")

    @commands.Component.listener()
    async def event_subscription_gift(
        self,
        payload: twitchio.ChannelSubscriptionGift,
    ) -> None:
        """贈禮訂閱事件

        Sends a configurable chat message and updates the gifter's cumulative count.
        Anonymous gifts are handled gracefully (shown as 匿名用戶 in message).
        """
        channel_id = payload.broadcaster.id
        broadcaster_name = payload.broadcaster.name

        if payload.anonymous or not payload.user:
            user_name = "匿名用戶"
        else:
            user_name = payload.user.display_name or payload.user.name or ""

        tier_name = tier_label(payload.tier)
        total = payload.total
        cumulative = payload.cumulative_total
        cumulative_str = str(cumulative) if cumulative is not None else "?"

        # Analytics — always write, even for a disabled greeting / non-mod bot.
        if not payload.anonymous and payload.user and cumulative is not None:
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

        await self._notify(
            channel_id,
            "gift_sub",
            {
                "user": user_name,
                "tier": tier_name,
                "total": str(total),
                "cumulative": cumulative_str,
            },
            label=f"[{broadcaster_name}] GiftSub: {user_name} x{total} ({tier_name})",
        )

    @commands.Component.listener()
    async def event_subscription_message(
        self,
        payload: twitchio.ChannelSubscriptionMessage,
    ) -> None:
        """重新訂閱事件（含訂閱留言）

        NOTE: always-on — fires via EventSub regardless of streaming state.
        """
        user_name = payload.user.display_name or payload.user.name or ""
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id
        tier_name = tier_label(payload.tier)
        months = payload.months
        streak = payload.streak_months if payload.streak_months is not None else 0

        await self._notify(
            channel_id,
            "resub",
            {
                "user": user_name,
                "tier": tier_name,
                "months": str(months),
                "streak": str(streak),
                "message": clean_message_var(payload.text),
            },
            label=f"[{broadcaster_name}] Resub: {user_name} ({tier_name} ×{months})",
        )

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

        label = f"[{broadcaster_name}] Cheer: {user_name} {bits_amount} bits"
        if not await self._notify(
            channel_id,
            "bits",
            {
                "user": user_name,
                "amount": str(bits_amount),
                "message": clean_message_var(payload.message or ""),
            },
            label=label,
        ):
            return

        try:
            session_id = self._session_id(channel_id)
            if session_id is not None:
                user_id = None if payload.anonymous else (payload.user.id if payload.user else None)
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
            LOGGER.warning(f"[{broadcaster_name}] Cheer analytics failed: {e}")

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

        if not self._bot_has_mod(broadcaster_id):
            LOGGER.debug(f"[{broadcaster_name}] Raid: {raider_name} (bot not mod, skipped)")
            return

        await self._notify(
            broadcaster_id,
            "raid",
            {"user": raider_name, "count": str(viewer_count)},
            label=f"[{broadcaster_name}] Raid: {raider_name} ({viewer_count})",
        )

        try:
            config = await self.event_configs.get_config(broadcaster_id, "raid")
        except Exception:
            config = None
        auto_shoutout = config.options.get("auto_shoutout", True) if config else True

        if auto_shoutout:
            try:
                await payload.to_broadcaster.send_shoutout(
                    to_broadcaster=raider_id,
                    moderator=self.bot.bot_id,
                )
                LOGGER.info(f"[{broadcaster_name}] Raid shoutout sent: {raider_name}")
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

        try:
            session_id = self._session_id(broadcaster_id)
            if session_id is not None:
                await self.bot.analytics.record_raid_event(
                    session_id=session_id,
                    channel_id=broadcaster_id,
                    from_broadcaster_id=raider_id,
                    from_broadcaster_name=payload.from_broadcaster.name or raider_name,
                    viewers=viewer_count,
                    occurred_at=datetime.now(UTC),
                )
        except Exception as e:
            LOGGER.warning(f"[{broadcaster_name}] Raid analytics failed: {e}")

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

        # Track when bot itself gets mod — unlocks all features
        if payload.user.id == self.bot.bot_id:
            self.bot._bot_is_mod.add(channel_id)  # type: ignore[attr-defined]
            LOGGER.info(f"[{payload.broadcaster.name}] Bot was granted mod — all features enabled")
            self._trigger_emote_sync(channel_id)
            # channel.follow subscription needs the bot as moderator — it 403s
            # if the channel was added before this grant. (Re)subscribe now.
            await self.bot.subs.resubscribe_follow(channel_id)

        try:
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

        # Track when bot itself loses mod — blocks all features
        if payload.user.id == self.bot.bot_id:
            self.bot._bot_is_mod.discard(channel_id)  # type: ignore[attr-defined]
            LOGGER.warning(f"[{payload.broadcaster.name}] Bot lost mod — all features blocked")
            self._trigger_emote_sync(channel_id)

        try:
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

    async def _record_vip(
        self, payload: twitchio.ChannelVIPAdd | twitchio.ChannelVIPRemove, *, is_vip: bool
    ) -> None:
        verb = "VIPAdd" if is_vip else "VIPRemove"
        user_name = payload.user.display_name or payload.user.name or ""
        try:
            await self.bot.analytics.upsert_viewer_vip_status(
                channel_id=payload.broadcaster.id,
                user_id=payload.user.id,
                username=payload.user.name or user_name,
                display_name=payload.user.display_name,
                is_vip=is_vip,
            )
            LOGGER.info(f"[{payload.broadcaster.name}] {verb}: {user_name}")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] {verb}: {user_name} (error: {e})")

    @commands.Component.listener()
    async def event_vip_add(self, payload: twitchio.ChannelVIPAdd) -> None:
        await self._record_vip(payload, is_vip=True)

    @commands.Component.listener()
    async def event_vip_remove(self, payload: twitchio.ChannelVIPRemove) -> None:
        await self._record_vip(payload, is_vip=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(EventComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
