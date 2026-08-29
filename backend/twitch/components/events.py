import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from shared.events import tier_label
from utils.event_render import clean_message_var, compose_note, mention_vars, render_template
from utils.reauth import is_scope_error, reauth_notifier

if TYPE_CHECKING:
    from core.bot import Bot


LOGGER: logging.Logger = logging.getLogger(__name__)


class EventsComponent(commands.Component):
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
        if not await self._notify(
            channel_id, "follow", mention_vars("user", user_name), label=label
        ):
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
        """訂閱狀態 / analytics only.

        The greeting is posted from ``event_chat_notification`` (the ``sub``
        notice), which — unlike ``channel.subscribe`` — carries the Prime flag.
        This handler only keeps ``viewer_channel_status`` and ``stream_events``
        current, including for gifted-sub recipients (``is_gift=True``).
        """
        user_name = payload.user.display_name or payload.user.name or ""
        broadcaster_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id

        try:
            await self.bot.analytics.upsert_viewer_subscription(
                channel_id=channel_id,
                user_id=payload.user.id,
                username=payload.user.name or user_name,
                display_name=payload.user.display_name,
                sub_tier=tier_label(payload.tier),
                sub_gifted=bool(payload.gift),
            )
        except Exception as e:
            LOGGER.warning(f"[{broadcaster_name}] Subscription status upsert failed: {e}")

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
            LOGGER.warning(f"[{broadcaster_name}] Subscribe analytics failed: {e}")

    @commands.Component.listener()
    async def event_subscription_gift(
        self,
        payload: twitchio.ChannelSubscriptionGift,
    ) -> None:
        """贈禮訂閱事件 — thanks the gifter once per batch (the per-recipient
        greeting is ``gift_recipient`` via ``event_chat_notification``).

        Anonymous gifts are handled gracefully (shown as 匿名用戶 in the message).
        """
        channel_id = payload.broadcaster.id
        broadcaster_name = payload.broadcaster.name

        anonymous = payload.anonymous or payload.user is None
        if payload.user is None:
            user_name = "匿名用戶"
        else:
            user_name = payload.user.display_name or payload.user.name or ""

        total = payload.total
        cumulative = payload.cumulative_total

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
                **mention_vars("user", user_name, anonymous=anonymous),
                "total": str(total),
                "cumulative": "" if cumulative is None else str(cumulative),
                "note": compose_note(tier=payload.tier),
            },
            label=f"[{broadcaster_name}] GiftSub: {user_name} x{total}",
        )

    @commands.Component.listener()
    async def event_chat_notification(
        self,
        payload: twitchio.ChatNotification,
    ) -> None:
        """sub / resub / sub_gift greetings.

        This is the only source carrying ``is_prime``, gifted-resub, and
        per-recipient gift data. Every other ``notice_type`` is ignored — the
        dedicated ``channel.subscription.*`` events own analytics.
        """
        nt = payload.notice_type
        if nt == "sub" and payload.sub is not None:
            await self._greet_sub(payload, payload.sub)
        elif nt == "resub" and payload.resub is not None:
            await self._greet_resub(payload, payload.resub)
        elif nt == "sub_gift" and payload.sub_gift is not None:
            await self._greet_gift_recipient(payload, payload.sub_gift)

    async def _greet_sub(self, payload: twitchio.ChatNotification, sub: twitchio.ChatSub) -> None:
        name = payload.chatter.display_name or payload.chatter.name or ""
        await self._notify(
            payload.broadcaster.id,
            "subscribe",
            {
                **mention_vars("user", name),
                "note": compose_note(prime=sub.prime, tier=sub.tier, months=sub.months),
            },
            label=f"[{payload.broadcaster.name}] Sub: {name}",
        )

    async def _greet_resub(
        self, payload: twitchio.ChatNotification, resub: twitchio.ChatResub
    ) -> None:
        name = payload.chatter.display_name or payload.chatter.name or ""
        await self._notify(
            payload.broadcaster.id,
            "resub",
            {
                **mention_vars("user", name),
                "total_months": str(resub.cumulative_months),
                "streak": "" if resub.streak_months is None else str(resub.streak_months),
                "message": clean_message_var(payload.text or ""),
                "note": compose_note(
                    gifted=resub.gift,
                    prime=resub.prime,
                    tier=resub.tier,
                    months=resub.months,
                ),
            },
            label=f"[{payload.broadcaster.name}] Resub: {name} (x{resub.cumulative_months})",
        )

    async def _greet_gift_recipient(
        self, payload: twitchio.ChatNotification, gift: twitchio.ChatSubGift
    ) -> None:
        channel_id = payload.broadcaster.id
        if payload.anonymous:
            return  # can't mention / thank an anonymous gifter
        if gift.community_gift_id is not None:
            # Part of a gift bomb — gift_sub already thanks the gifter once.
            try:
                config = await self.event_configs.get_config(channel_id, "gift_recipient")
            except Exception:
                config = None
            if not config or config.options.get("skip_bombs", True):
                return
        gifter = payload.chatter.display_name or payload.chatter.name or ""
        recipient = gift.recipient.display_name or gift.recipient.name or ""
        await self._notify(
            channel_id,
            "gift_recipient",
            {
                **mention_vars("gifter", gifter),
                **mention_vars("user", recipient),
                "note": compose_note(tier=gift.tier, months=gift.months),
            },
            label=f"[{payload.broadcaster.name}] GiftRecipient: {recipient} <- {gifter}",
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
                **mention_vars("user", user_name, anonymous=payload.anonymous),
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
        raider_login = payload.from_broadcaster.name
        raider_url = f"https://twitch.tv/{raider_login}" if raider_login else ""
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
            {
                **mention_vars("user", raider_name),
                "count": str(viewer_count),
                "url": raider_url,
            },
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
    await bot.add_component(EventsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
