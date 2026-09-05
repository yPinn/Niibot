import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiohttp
import asyncpg
import twitchio
from cachetools import TTLCache  # type: ignore[import-untyped]
from twitchio.ext import commands

from core.config import get_settings
from shared.models.vip import (
    VipRedemptionDecision,
    VipRedemptionStatus,
    VipRewardRule,
    VipSnapshotMember,
)
from shared.repositories.activation_code import ActivationCodeRepository
from shared.repositories.attendance import AttendanceRepository
from shared.repositories.command_config import RedemptionConfigRepository
from shared.repositories.game_queue import GameQueueRepository, GameQueueSettingsRepository
from shared.repositories.video_queue import (
    SOURCE_PRIORITY,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
)
from shared.repositories.vip import VipRepository
from shared.services.attendance import AttendanceService
from shared.services.vip import VipService, add_calendar_months
from shared.video_sources import fetch_video_metadata, resolve_video_url, unplayable_message
from utils.mod_guard import mod_guard_notifier
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
        self.activation_repo = ActivationCodeRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.attendance = AttendanceService(AttendanceRepository(self.bot.token_database))  # type: ignore[attr-defined]
        self.gq_repo = GameQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.gq_settings_repo = GameQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_repo = VideoQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_settings_repo = VideoQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vip_repo = VipRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vip_policy = VipService()
        self._session: aiohttp.ClientSession | None = None
        self._vip_channel_locks: dict[str, asyncio.Lock] = {}
        self._vip_expiry_task: asyncio.Task[None] | None = None
        # EventSub delivers at-least-once; dedupe redemptions by id so a
        # redelivery (e.g. around conduit shard reassociation/reconnect) is
        # neither re-logged nor reprocessed. TTL comfortably exceeds Twitch's
        # redelivery window; maxsize keeps memory bounded.
        self._seen_redemptions: TTLCache = TTLCache(maxsize=2048, ttl=600)

    def refresh_pool(self, pool) -> None:
        self.redemption_repo.pool = pool
        self.activation_repo.pool = pool
        self.attendance.repository.pool = pool
        self.gq_repo.pool = pool
        self.gq_settings_repo.pool = pool
        self.vq_repo.pool = pool
        self.vq_settings_repo.pool = pool
        self.vip_repo.pool = pool

    async def component_load(self) -> None:
        self._session = aiohttp.ClientSession()
        self._vip_expiry_task = asyncio.create_task(self._vip_expiry_loop())
        LOGGER.info("ChannelPoints component loaded")

    async def component_teardown(self) -> None:
        if self._vip_expiry_task is not None:
            self._vip_expiry_task.cancel()
            try:
                await self._vip_expiry_task
            except asyncio.CancelledError:
                pass
            self._vip_expiry_task = None
        if self._session:
            await self._session.close()
            self._session = None
        LOGGER.info("ChannelPoints component unloaded")

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
        if payload.id in self._seen_redemptions:
            LOGGER.debug("Duplicate redemption %s ignored (EventSub redelivery)", payload.id)
            return
        self._seen_redemptions[payload.id] = True

        LOGGER.debug("event_custom_redemption_add triggered: %s", type(payload).__name__)

        channel_name = payload.broadcaster.name
        channel_id = payload.broadcaster.id
        user_name = payload.user.display_name or payload.user.name
        reward_title = payload.reward.title
        reward_cost = payload.reward.cost
        user_input = payload.user_input or ""

        LOGGER.info(
            "[%s] %s redeemed '%s' (%s pts)", channel_name, user_name, reward_title, reward_cost
        )
        if user_input:
            LOGGER.debug("[%s] User input: %s", channel_name, user_input)

        if channel_id in self.bot._needs_reauth:  # type: ignore[attr-defined]
            from utils.reauth import reauth_notifier

            await reauth_notifier.notify(
                broadcaster_login=channel_name or "",
                channel_id=channel_id,
                send_fn=lambda msg: self._reply(payload.broadcaster, msg),
            )
            return

        if channel_id not in self.bot._bot_is_mod:  # type: ignore[attr-defined]
            if channel_id in self.bot._mod_check_pending:  # type: ignore[attr-defined]
                LOGGER.debug("[%s] Redemption deferred: mod check in-flight", channel_name)
                return
            LOGGER.debug("[%s] Redemption skipped: bot not mod", channel_name)
            bot_login: str = getattr(self.bot, "_bot_login", "niibot")
            await mod_guard_notifier.notify(
                broadcaster_login=channel_name or "",
                channel_id=channel_id,
                bot_login=bot_login,
                send_fn=lambda msg: self._reply(payload.broadcaster, msg),
            )
            return

        await self._handle_redemption(payload)

    async def _handle_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """處理兌換事件（DB 驅動比對）"""
        reward_title = payload.reward.title
        reward_id = str(payload.reward.id)
        user_name = payload.user.display_name or payload.user.name
        channel_id = payload.broadcaster.id

        channel_name = payload.broadcaster.name

        vip_rule = await self.vip_repo.get_reward_rule(
            channel_id=str(channel_id), reward_id=reward_id
        )
        if vip_rule is not None:
            if not vip_rule.enabled:
                LOGGER.debug("[%s] Timed VIP reward is disabled: %s", channel_name, reward_title)
                return
            await self._handle_timed_vip_redemption(payload, vip_rule)
            return

        config = await self.redemption_repo.find_by_reward(channel_id, reward_id, reward_title)
        if not config:
            LOGGER.debug("[%s] No matching redemption config for: %s", channel_name, reward_title)
            return

        if config.action_type == "niibot_auth" and user_name:
            owner_id = self.settings.owner_id
            if channel_id == owner_id:
                await self._handle_niibot_redemption(payload, user_name)
            else:
                LOGGER.warning(
                    "[%s] %s attempted niibot_auth on non-owner channel", channel_name, user_name
                )
        elif config.action_type == "first" and user_name:
            await self._handle_first_redemption(payload, user_name)
        elif config.action_type == "vip":
            await self._handle_vip_redemption(payload, user_name)
        elif config.action_type == "game_queue" and user_name:
            await self._handle_game_queue_redemption(payload, user_name)
        elif config.action_type == "video_queue" and user_name:
            await self._handle_video_queue_redemption(payload, user_name)
        elif config.action_type == "checkin" and user_name:
            await self._handle_checkin_redemption(payload)

    async def _handle_checkin_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """Apply a Twitch-managed reward to the shared daily check-in domain."""
        broadcaster = payload.broadcaster
        channel_id = str(broadcaster.id)
        user_id = str(payload.user.id)
        username = payload.user.name or user_id
        display_name = payload.user.display_name or None
        session_id = self.bot.sessions.session_id(channel_id) or None

        try:
            outcome = await self.attendance.check_in_with_reply(
                channel_id=channel_id,
                user_id=user_id,
                username=username,
                display_name=display_name,
                session_id=session_id,
            )
            if outcome.delay_seconds > 0:
                await asyncio.sleep(outcome.delay_seconds)
            await self._reply(broadcaster, outcome.message)
        except Exception:
            LOGGER.exception(
                "Channel Points check-in failed",
                extra={"channel_id": channel_id, "user_id": user_id},
            )
            try:
                await self._reply(broadcaster, f"@{display_name or username} 簽到失敗，請稍後再試")
            except Exception:
                pass

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
                LOGGER.info("[%s] VIP granted to %s", channel_name, user_name)
            except Exception as e:
                LOGGER.warning("[%s] VIP granted but failed to send message: %s", channel_name, e)

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
                        "[%s] %s is already a moderator, cannot grant VIP", channel_name, user_name
                    )
                    error_message = f"@{user_name} 你已經是 Moderator 了！"
                elif "already a vip" in body:
                    LOGGER.info("[%s] %s is already a VIP", channel_name, user_name)
                    error_message = f"@{user_name} 你已經是 VIP 了！"
                else:
                    LOGGER.error("[%s] Failed to grant VIP (422): %s", channel_name, e)
                    error_message = f"@{user_name} VIP 授予失敗，請聯繫管理員！"
            else:
                LOGGER.error("[%s] Failed to grant VIP: %s", channel_name, e)
                error_message = f"@{user_name} VIP 授予失敗，請聯繫管理員！"

            try:
                await self._reply(broadcaster, error_message)
            except Exception:
                pass

    async def _fetch_vip_snapshot(
        self, broadcaster: twitchio.PartialUser
    ) -> tuple[VipSnapshotMember, ...]:
        members: list[VipSnapshotMember] = []
        async for user in broadcaster.fetch_vips(first=100):
            user_id = str(user.id)
            members.append(
                VipSnapshotMember(
                    user_id=user_id,
                    user_login=user.name or user_id,
                    display_name=user.display_name or None,
                )
            )
        return tuple(members)

    async def _is_current_vip(self, broadcaster: twitchio.PartialUser, user_id: str) -> bool:
        async for _user in broadcaster.fetch_vips(user_ids=[user_id], first=1, max_results=1):
            return True
        return False

    async def _vip_expiry_loop(self) -> None:
        consecutive_failures = 0
        while True:
            try:
                await self._recover_granting_vips()
                await self._expire_due_vips()
                consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                consecutive_failures += 1
                LOGGER.exception(
                    "Timed VIP expiry loop failed (consecutive=%d)", consecutive_failures
                )
            # Steady state runs every minute. On a sustained failure (e.g. the
            # DB schema is not migrated yet) back off exponentially up to 30
            # minutes so a broken dependency does not flood the logs.
            if consecutive_failures == 0:
                delay = 60
            else:
                delay = min(60 * 2**consecutive_failures, 1800)
            await asyncio.sleep(delay)

    async def _recover_granting_vips(self) -> None:
        """Repair Add-VIP success followed by a local persistence interruption."""
        now = datetime.now(UTC)
        granting = await self.vip_repo.list_stale_granting(now=now, limit=50)
        for event in granting:
            if event.rule_id is None:
                await self.vip_repo.transition_redemption(
                    channel_id=event.channel_id,
                    redemption_id=event.redemption_id,
                    status=VipRedemptionStatus.FAILED,
                    error_code="vip_rule_missing_during_recovery",
                )
                continue
            lock = self._vip_channel_locks.setdefault(event.channel_id, asyncio.Lock())
            async with lock:
                try:
                    broadcaster = self.bot.create_partialuser(user_id=event.channel_id)
                    if not await self._is_current_vip(broadcaster, event.user_id):
                        await self.vip_repo.transition_redemption(
                            channel_id=event.channel_id,
                            redemption_id=event.redemption_id,
                            status=VipRedemptionStatus.FAILED,
                            error_code="twitch_vip_grant_not_observed",
                        )
                        continue
                    if event.is_permanent_snapshot:
                        expires_at = None
                    elif event.duration_months_snapshot is None:
                        await self.vip_repo.transition_redemption(
                            channel_id=event.channel_id,
                            redemption_id=event.redemption_id,
                            status=VipRedemptionStatus.FAILED,
                            error_code="vip_duration_missing_during_recovery",
                        )
                        continue
                    else:
                        expires_at = add_calendar_months(
                            event.occurred_at,
                            event.duration_months_snapshot,
                        )
                    await self.vip_repo.apply_managed_entitlement(
                        channel_id=event.channel_id,
                        user_id=event.user_id,
                        user_login=event.user_login,
                        display_name=event.display_name,
                        granted_at=event.occurred_at,
                        expires_at=expires_at,
                        is_permanent=event.is_permanent_snapshot,
                        reward_rule_id=event.rule_id,
                        synced_at=now,
                    )
                    await self.vip_repo.transition_redemption(
                        channel_id=event.channel_id,
                        redemption_id=event.redemption_id,
                        status=VipRedemptionStatus.GRANTED,
                        error_code=None,
                    )
                except Exception:
                    LOGGER.exception(
                        "Timed VIP granting recovery failed",
                        extra={
                            "channel_id": event.channel_id,
                            "redemption_id": event.redemption_id,
                        },
                    )

    async def _expire_due_vips(self) -> None:
        now = datetime.now(UTC)
        due = await self.vip_repo.claim_due_entitlements(now=now, limit=50)
        for entitlement in due:
            lock = self._vip_channel_locks.setdefault(entitlement.channel_id, asyncio.Lock())
            async with lock:
                try:
                    broadcaster = self.bot.create_partialuser(user_id=entitlement.channel_id)
                    if not await self._is_current_vip(broadcaster, entitlement.user_id):
                        await self.vip_repo.finish_expiry(
                            channel_id=entitlement.channel_id,
                            entitlement_id=entitlement.id,
                            removed_at=now,
                            externally_removed=True,
                        )
                        continue
                    user = self.bot.create_partialuser(user_id=entitlement.user_id)
                    await broadcaster.remove_vip(user=user)
                    await self.vip_repo.finish_expiry(
                        channel_id=entitlement.channel_id,
                        entitlement_id=entitlement.id,
                        removed_at=now,
                        externally_removed=False,
                    )
                    # Twitch allows 10 VIP mutations per 10 seconds. A small
                    # per-operation delay keeps this worker below that ceiling.
                    await asyncio.sleep(1.05)
                except Exception:
                    await self.vip_repo.release_expiry_claim(
                        channel_id=entitlement.channel_id,
                        entitlement_id=entitlement.id,
                    )
                    LOGGER.exception(
                        "Timed VIP expiry failed",
                        extra={
                            "channel_id": entitlement.channel_id,
                            "user_id": entitlement.user_id,
                        },
                    )

    @commands.Component.listener()
    async def event_vip_add(self, payload: twitchio.ChannelVIPAdd) -> None:
        """Track manual Twitch VIP additions as external ownership."""
        user_id = str(payload.user.id)
        await self.vip_repo.observe_vip_added(
            channel_id=str(payload.broadcaster.id),
            member=VipSnapshotMember(
                user_id=user_id,
                user_login=payload.user.name or user_id,
                display_name=payload.user.display_name or None,
            ),
            observed_at=datetime.now(UTC),
        )

    @commands.Component.listener()
    async def event_vip_remove(self, payload: twitchio.ChannelVIPRemove) -> None:
        """Treat Twitch removal as authoritative and close local scheduling."""
        await self.vip_repo.mark_removed_external(
            channel_id=str(payload.broadcaster.id),
            user_id=str(payload.user.id),
            synced_at=datetime.now(UTC),
        )

    async def _handle_timed_vip_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        rule: VipRewardRule,
    ) -> None:
        """Reconcile Twitch state and process a durable timed VIP redemption."""
        broadcaster = payload.broadcaster
        channel_id = str(broadcaster.id)
        redemption_id = str(payload.id)
        user_id = str(payload.user.id)
        user_login = payload.user.name or user_id
        display_name = payload.user.display_name or None
        occurred = getattr(payload, "redeemed_at", None)
        occurred_at = occurred if isinstance(occurred, datetime) else datetime.now(UTC)

        receipt = await self.vip_repo.record_redemption(
            channel_id=channel_id,
            redemption_id=redemption_id,
            rule_id=rule.id,
            reward_id=rule.reward_id,
            reward_name=rule.reward_name_snapshot,
            user_id=user_id,
            user_login=user_login,
            display_name=display_name,
            duration_months=rule.duration_months,
            is_permanent=rule.is_permanent,
            occurred_at=occurred_at,
        )
        if receipt.status is not VipRedemptionStatus.RECEIVED:
            LOGGER.info(
                "[%s] VIP redemption %s already processed as %s",
                broadcaster.name,
                redemption_id,
                receipt.status,
            )
            return

        settings = await self.vip_repo.get_or_create_settings(channel_id)
        if settings.tracking_started_at is None or settings.slot_limit is None:
            await self.vip_repo.transition_redemption(
                channel_id=channel_id,
                redemption_id=redemption_id,
                status=VipRedemptionStatus.NOT_INITIALIZED,
                error_code="vip_tracking_not_initialized",
            )
            await self._reply(
                broadcaster,
                f"@{display_name or user_login} VIP 管理尚未完成初次清點，請通知主播人工退款。",
            )
            return

        lock = self._vip_channel_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            remote_granted = False
            try:
                snapshot = await self._fetch_vip_snapshot(broadcaster)
                await self.vip_repo.reconcile_snapshot(
                    channel_id=channel_id,
                    members=snapshot,
                    synced_at=occurred_at,
                )
                entitlement = await self.vip_repo.get_entitlement(
                    channel_id=channel_id, user_id=user_id
                )
                plan = self.vip_policy.plan_redemption(
                    entitlement=entitlement,
                    rule=rule,
                    redeemed_at=occurred_at,
                )

                if plan.action is VipRedemptionDecision.NEEDS_REVIEW:
                    await self.vip_repo.transition_redemption(
                        channel_id=channel_id,
                        redemption_id=redemption_id,
                        status=VipRedemptionStatus.NEEDS_REVIEW_EXTERNAL_VIP,
                        error_code="external_vip_requires_review",
                    )
                    await self._reply(
                        broadcaster,
                        f"@{display_name or user_login} 已是外部 VIP，需由主播人工確認是否納入期限管理與退款。",
                    )
                    return

                if plan.action is VipRedemptionDecision.NOOP_PERMANENT:
                    await self.vip_repo.transition_redemption(
                        channel_id=channel_id,
                        redemption_id=redemption_id,
                        status=VipRedemptionStatus.EXTENDED,
                        error_code=None,
                    )
                    await self._reply(
                        broadcaster,
                        f"@{display_name or user_login} 已是永久 VIP，現有資格不會被縮短。",
                    )
                    return

                is_current_vip = any(member.user_id == user_id for member in snapshot)
                if not is_current_vip:
                    active_count = await self.vip_repo.count_active(channel_id)
                    if active_count >= settings.slot_limit:
                        await self.vip_repo.transition_redemption(
                            channel_id=channel_id,
                            redemption_id=redemption_id,
                            status=VipRedemptionStatus.CAPACITY_FULL,
                            error_code="vip_capacity_full",
                        )
                        await self._reply(
                            broadcaster,
                            f"@{display_name or user_login} VIP 名額已滿，請通知主播或 Mod 人工退款。",
                        )
                        return
                    await self.vip_repo.transition_redemption(
                        channel_id=channel_id,
                        redemption_id=redemption_id,
                        status=VipRedemptionStatus.GRANTING,
                        error_code=None,
                    )
                    await broadcaster.add_vip(user=payload.user)
                    remote_granted = True

                if rule.id is None:
                    raise RuntimeError("Persisted VIP reward rule is missing its id")
                await self.vip_repo.apply_managed_entitlement(
                    channel_id=channel_id,
                    user_id=user_id,
                    user_login=user_login,
                    display_name=display_name,
                    granted_at=plan.granted_at,
                    expires_at=plan.expires_at,
                    is_permanent=plan.is_permanent,
                    reward_rule_id=rule.id,
                    synced_at=occurred_at,
                )
                final_status = (
                    VipRedemptionStatus.GRANTED
                    if plan.action is VipRedemptionDecision.GRANT
                    else VipRedemptionStatus.EXTENDED
                )
                await self.vip_repo.transition_redemption(
                    channel_id=channel_id,
                    redemption_id=redemption_id,
                    status=final_status,
                    error_code=None,
                )
                verb = "授予" if final_status is VipRedemptionStatus.GRANTED else "延長"
                await self._reply(
                    broadcaster,
                    f"@{display_name or user_login} VIP 已{verb}；期限以 Niibot 後台顯示的預計到期為準。",
                )
            except Exception as exc:
                if remote_granted:
                    # Keep the durable row in GRANTING. The recovery pass will
                    # verify Twitch state and finish the local entitlement.
                    LOGGER.exception(
                        "Timed VIP granted remotely; local persistence deferred",
                        extra={
                            "channel_id": channel_id,
                            "redemption_id": redemption_id,
                        },
                    )
                    return
                if is_scope_error(exc):
                    await reauth_notifier.notify(
                        broadcaster_login=broadcaster.name or "",
                        channel_id=channel_id,
                        send_fn=lambda msg: self._reply(broadcaster, msg),
                    )
                    return
                status_code = getattr(exc, "status", None) or getattr(exc, "status_code", None)
                if status_code == 409:
                    status = VipRedemptionStatus.CAPACITY_FULL
                    error_code = "twitch_vip_capacity_full"
                elif status_code == 422 and "moderator" in str(exc).lower():
                    status = VipRedemptionStatus.MODERATOR_CONFLICT
                    error_code = "twitch_user_is_moderator"
                else:
                    status = VipRedemptionStatus.FAILED
                    error_code = "twitch_vip_grant_failed"
                await self.vip_repo.transition_redemption(
                    channel_id=channel_id,
                    redemption_id=redemption_id,
                    status=status,
                    error_code=error_code,
                )
                LOGGER.exception(
                    "Timed VIP redemption failed",
                    extra={"channel_id": channel_id, "redemption_id": redemption_id},
                )
                try:
                    await self._reply(
                        broadcaster,
                        f"@{display_name or user_login} VIP 兌換失敗，請通知主播或 Mod 查明原因並人工退款。",
                    )
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
                LOGGER.info("[%s] First claimed by %s", channel_name, user_name)
            except Exception as e:
                LOGGER.error("[%s] First announcement failed, falling back: %s", channel_name, e)
                try:
                    await self._reply(broadcaster, f"@{user_name} 恭喜你搶到第一！")
                    LOGGER.info("[%s] First fallback message sent to %s", channel_name, user_name)
                except Exception as fallback_error:
                    LOGGER.error(
                        "[%s] First fallback also failed: %s", channel_name, fallback_error
                    )

        except Exception as e:
            LOGGER.error("[%s] First claim error: %s", channel_name, e)

    async def _handle_niibot_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理 Niibot 獎勵兌換：記錄兌換憑證，登入時自動啟用。"""
        channel_name = payload.broadcaster.name
        broadcaster = payload.broadcaster
        platform_user_id = str(payload.user.id)

        try:
            code = await self.activation_repo.create_channel_points_grant(
                platform_user_id,
                redemption_id=str(payload.id),
                channel_id=str(payload.broadcaster.id),
                reward_cost=payload.reward.cost,
            )
        except Exception as e:
            LOGGER.error("[%s] Niibot auth: failed to record activation grant: %s", channel_name, e)
            try:
                await self._reply(broadcaster, f"@{user_name} 兌換失敗，請稍後再試！")
            except Exception:
                pass
            return

        try:
            await self._reply(
                broadcaster, f"@{user_name} 登入 Niibot 即可啟用！啟用碼也已私訊給你。"
            )
            LOGGER.info("[%s] Niibot auth: confirmation sent to %s", channel_name, user_name)
        except Exception as e:
            LOGGER.warning("[%s] Niibot auth: failed to send public message: %s", channel_name, e)

        frontend_url = self.settings.frontend_url
        whisper_message = (
            f"前往 {frontend_url} 用 Twitch 登入即會自動啟用。"
            f"若未生效，可於啟用頁輸入啟用碼： {code}（72 小時內有效）"
        )
        try:
            bot_user = self.bot.create_partialuser(user_id=self.bot.bot_id)
            await bot_user.send_whisper(
                to_user=payload.user,
                message=whisper_message,
            )
            LOGGER.info("[%s] Niibot auth: whisper sent to %s", channel_name, user_name)
        except Exception as e:
            LOGGER.error("[%s] Niibot auth: failed to send whisper: %s", channel_name, e)
            if is_scope_error(e):
                await reauth_notifier.notify(
                    broadcaster_login=channel_name or "",
                    channel_id=str(broadcaster.id),
                    send_fn=lambda msg: self._reply(broadcaster, msg),
                )
            try:
                await self._reply(
                    broadcaster,
                    f"@{user_name} 私訊發送失敗，請聯繫 @llazypilot 獲取啟用碼！",
                )
            except Exception as fallback_error:
                LOGGER.error(
                    "[%s] Niibot auth: fallback also failed: %s", channel_name, fallback_error
                )

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
                    "[%s] GameQueue: duplicate entry race for %s", broadcaster.name, user_name
                )
                return

            position = await self.gq_repo.count_active(channel_id)
            await self._reply(broadcaster, f"@{user_name} 已加入隊列，第{position}位")
            LOGGER.info(
                "[%s] GameQueue: %s joined (position %s)", broadcaster.name, user_name, position
            )

        except Exception as e:
            if is_scope_error(e):
                await reauth_notifier.notify(
                    broadcaster_login=broadcaster.name or "",
                    channel_id=str(broadcaster.id),
                    send_fn=lambda msg: self._reply(broadcaster, msg),
                )
                return
            LOGGER.error("[%s] GameQueue error: %s", broadcaster.name, e)

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

            resolved = await resolve_video_url(user_input, session=self._session)
            if resolved is None:
                await self._reply(
                    broadcaster,
                    f"@{user_name} 請在兌換時輸入有效的 YouTube、Twitch Clip 或 Bilibili 連結",
                )
                return

            if await self.vq_repo.video_is_active(channel_id, resolved.video_id):
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

            metadata = await fetch_video_metadata(
                resolved,
                youtube_api_key=self.settings.youtube_api_key,
                twitch_client_id=self.settings.twitch_client_id,
                twitch_client_secret=self.settings.twitch_client_secret,
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
                await self._reply(
                    broadcaster,
                    f"@{user_name} {unplayable_message(metadata.unplayable_reason)}",
                )
                return

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

            if settings.max_duration_redemption > 0:
                if duration_seconds is None:
                    await self._reply(broadcaster, f"@{user_name} 無法驗證影片時長，請稍後再試")
                    return
                if duration_seconds > settings.max_duration_redemption:
                    max_m, max_s = divmod(settings.max_duration_redemption, 60)
                    vid_m, vid_s = divmod(duration_seconds, 60)
                    await self._reply(
                        broadcaster,
                        f"@{user_name} 影片長度 {vid_m}:{vid_s:02d} 超過上限 {max_m}:{max_s:02d}",
                    )
                    return

            entry = await self.vq_repo.add_if_within_limits(
                channel_id=channel_id,
                video_id=resolved.video_id,
                requested_by=user_name,
                source="redemption",
                max_queue_size=settings.max_queue_size,
                max_per_user=settings.max_per_user,
                requested_by_id=user_id,
                title=title,
                duration_seconds=duration_seconds,
                is_vertical=metadata.is_vertical,
                video_type=resolved.video_type,
                priority=SOURCE_PRIORITY["redemption"],
            )
            if entry is None:
                await self._reply(broadcaster, f"@{user_name} 點歌失敗，佇列狀態已變更，請重試")
                return
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
            LOGGER.info(
                "[%s] VideoQueue: %s added '%s' (position %s)",
                broadcaster.name,
                user_name,
                title or resolved.video_id,
                position,
            )

        except Exception as e:
            if is_scope_error(e):
                await reauth_notifier.notify(
                    broadcaster_login=broadcaster.name or "",
                    channel_id=str(broadcaster.id),
                    send_fn=lambda msg: self._reply(broadcaster, msg),
                )
                return
            LOGGER.error("[%s] VideoQueue error: %s", broadcaster.name, e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(ChannelPointsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
