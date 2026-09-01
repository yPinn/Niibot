"""Pure timed VIP policy decisions shared by API and Twitch adapters."""

from __future__ import annotations

import calendar
from datetime import datetime

from shared.models.vip import (
    VipChannelSettings,
    VipDashboardState,
    VipEntitlement,
    VipEntitlementSource,
    VipEntitlementStatus,
    VipRedemptionDecision,
    VipRedemptionPlan,
    VipRedemptionStatus,
    VipRewardRule,
    VipSnapshotMember,
)
from shared.repositories.vip import VipRepository

DEFAULT_VIP_DURATION_MONTHS = 3
MAX_VIP_DURATION_MONTHS = 120


def add_calendar_months(value: datetime, months: int) -> datetime:
    """Add calendar months while clamping month-end to the last valid day."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("value must be timezone-aware")
    if months < 1:
        raise ValueError("months must be positive")

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class VipService:
    def __init__(self, repository: VipRepository | None = None) -> None:
        self.repository = repository

    def _repository(self) -> VipRepository:
        if self.repository is None:
            raise RuntimeError("VipService repository is not configured")
        return self.repository

    async def get_state(self, channel_id: str) -> VipDashboardState:
        repository = self._repository()
        settings = await repository.get_or_create_settings(channel_id)
        rules = await repository.list_reward_rules(channel_id)
        entitlements = await repository.list_entitlements(channel_id)
        redemptions = await repository.list_redemptions(channel_id)
        return VipDashboardState(
            settings=settings,
            rules=rules,
            entitlements=entitlements,
            redemptions=redemptions,
        )

    async def update_slot_limit(self, *, channel_id: str, slot_limit: int) -> VipChannelSettings:
        if not 1 <= slot_limit <= 500:
            raise ValueError("slot_limit must be between 1 and 500")
        return await self._repository().update_slot_limit(
            channel_id=channel_id, slot_limit=slot_limit
        )

    async def initialize(
        self,
        *,
        channel_id: str,
        slot_limit: int,
        members: tuple[VipSnapshotMember, ...],
        synced_at: datetime,
    ) -> VipChannelSettings:
        return await self._repository().initialize_snapshot(
            channel_id=channel_id,
            slot_limit=slot_limit,
            members=members,
            synced_at=synced_at,
        )

    async def reconcile(
        self,
        *,
        channel_id: str,
        members: tuple[VipSnapshotMember, ...],
        synced_at: datetime,
    ) -> None:
        settings = await self._repository().get_or_create_settings(channel_id)
        if settings.tracking_started_at is None:
            raise ValueError("VIP tracking is not initialized")
        await self._repository().reconcile_snapshot(
            channel_id=channel_id,
            members=members,
            synced_at=synced_at,
        )

    async def require_active_entitlement(self, *, channel_id: str, user_id: str) -> VipEntitlement:
        entitlement = await self._repository().get_entitlement(
            channel_id=channel_id, user_id=user_id
        )
        if entitlement is None or entitlement.status is not VipEntitlementStatus.ACTIVE:
            raise ValueError("active VIP entitlement was not found")
        return entitlement

    async def record_manual_removal(
        self, *, channel_id: str, user_id: str, removed_at: datetime
    ) -> None:
        await self._repository().mark_removed_external(
            channel_id=channel_id,
            user_id=user_id,
            synced_at=removed_at,
        )

    async def upsert_rule(
        self,
        *,
        channel_id: str,
        reward_id: str,
        reward_name: str,
        duration_months: int | None = DEFAULT_VIP_DURATION_MONTHS,
        is_permanent: bool = False,
        enabled: bool = True,
    ) -> VipRewardRule:
        rule = self.build_rule(
            channel_id=channel_id,
            reward_id=reward_id,
            reward_name=reward_name,
            duration_months=duration_months,
            is_permanent=is_permanent,
            enabled=enabled,
        )
        return await self._repository().upsert_reward_rule(rule)

    async def set_rules_enabled(
        self, *, channel_id: str, enabled: bool
    ) -> tuple[VipRewardRule, ...]:
        return await self._repository().set_rules_enabled(channel_id=channel_id, enabled=enabled)

    async def adopt_external_redemption(
        self,
        *,
        channel_id: str,
        redemption_id: str,
        adopted_at: datetime,
        duration_months: int | None,
        is_permanent: bool,
    ) -> VipEntitlement:
        repository = self._repository()
        event = await repository.get_redemption(channel_id=channel_id, redemption_id=redemption_id)
        if event is None or event.status is not VipRedemptionStatus.NEEDS_REVIEW_EXTERNAL_VIP:
            raise ValueError("redemption is not awaiting external VIP review")
        if event.rule_id is None:
            raise ValueError("redemption has no persisted VIP rule")
        entitlement = await repository.get_entitlement(channel_id=channel_id, user_id=event.user_id)
        if (
            entitlement is None
            or entitlement.status is not VipEntitlementStatus.ACTIVE
            or entitlement.source is VipEntitlementSource.MANAGED
        ):
            raise ValueError("external VIP is no longer active")
        if is_permanent:
            if duration_months is not None:
                raise ValueError("permanent adoption cannot have duration_months")
            expires_at = None
        else:
            months = duration_months or event.duration_months_snapshot
            if months is None or not 1 <= months <= MAX_VIP_DURATION_MONTHS:
                raise ValueError("duration_months must be between 1 and 120")
            expires_at = add_calendar_months(adopted_at, months)

        managed = await repository.apply_managed_entitlement(
            channel_id=channel_id,
            user_id=event.user_id,
            user_login=event.user_login,
            display_name=event.display_name,
            granted_at=adopted_at,
            expires_at=expires_at,
            is_permanent=is_permanent,
            reward_rule_id=event.rule_id,
            synced_at=adopted_at,
        )
        await repository.transition_redemption(
            channel_id=channel_id,
            redemption_id=redemption_id,
            status=VipRedemptionStatus.ADOPTED,
            error_code=None,
        )
        return managed

    async def keep_external_redemption(self, *, channel_id: str, redemption_id: str) -> None:
        repository = self._repository()
        event = await repository.get_redemption(channel_id=channel_id, redemption_id=redemption_id)
        if event is None or event.status is not VipRedemptionStatus.NEEDS_REVIEW_EXTERNAL_VIP:
            raise ValueError("redemption is not awaiting external VIP review")
        await repository.transition_redemption(
            channel_id=channel_id,
            redemption_id=redemption_id,
            status=VipRedemptionStatus.KEPT_EXTERNAL,
            error_code="manual_refund_required",
        )

    async def adjust_entitlement(
        self,
        *,
        channel_id: str,
        user_id: str,
        adjusted_at: datetime,
        duration_months: int | None,
        is_permanent: bool,
    ) -> VipEntitlement:
        repository = self._repository()
        entitlement = await repository.get_entitlement(channel_id=channel_id, user_id=user_id)
        if (
            entitlement is None
            or entitlement.status is not VipEntitlementStatus.ACTIVE
            or entitlement.source is not VipEntitlementSource.MANAGED
            or entitlement.last_reward_rule_id is None
        ):
            raise ValueError("managed active VIP entitlement was not found")
        if is_permanent:
            if duration_months is not None:
                raise ValueError("permanent entitlement cannot have duration_months")
            expires_at = None
        else:
            if duration_months is None or not 1 <= duration_months <= MAX_VIP_DURATION_MONTHS:
                raise ValueError("duration_months must be between 1 and 120")
            expires_at = add_calendar_months(adjusted_at, duration_months)
        return await repository.apply_managed_entitlement(
            channel_id=channel_id,
            user_id=entitlement.user_id,
            user_login=entitlement.user_login,
            display_name=entitlement.display_name,
            granted_at=entitlement.granted_at or adjusted_at,
            expires_at=expires_at,
            is_permanent=is_permanent,
            reward_rule_id=entitlement.last_reward_rule_id,
            synced_at=adjusted_at,
        )

    @staticmethod
    def build_rule(
        *,
        channel_id: str,
        reward_id: str,
        reward_name: str,
        duration_months: int | None = DEFAULT_VIP_DURATION_MONTHS,
        is_permanent: bool = False,
        enabled: bool = True,
        rule_id: int | None = None,
    ) -> VipRewardRule:
        channel_id = channel_id.strip()
        reward_id = reward_id.strip()
        reward_name = reward_name.strip()
        if not channel_id:
            raise ValueError("channel_id is required")
        if not 1 <= len(reward_id) <= 128:
            raise ValueError("reward_id must be between 1 and 128 characters")
        if not 1 <= len(reward_name) <= 256:
            raise ValueError("reward_name must be between 1 and 256 characters")
        if is_permanent:
            if duration_months is not None:
                raise ValueError("permanent VIP rules cannot have a duration")
        elif duration_months is None or not 1 <= duration_months <= MAX_VIP_DURATION_MONTHS:
            raise ValueError("duration_months must be between 1 and 120")

        return VipRewardRule(
            id=rule_id,
            channel_id=channel_id,
            reward_id=reward_id,
            reward_name_snapshot=reward_name,
            duration_months=duration_months,
            is_permanent=is_permanent,
            enabled=enabled,
        )

    @staticmethod
    def plan_redemption(
        *,
        entitlement: VipEntitlement | None,
        rule: VipRewardRule,
        redeemed_at: datetime,
    ) -> VipRedemptionPlan:
        if redeemed_at.tzinfo is None or redeemed_at.utcoffset() is None:
            raise ValueError("redeemed_at must be timezone-aware")
        VipService.build_rule(
            channel_id=rule.channel_id,
            reward_id=rule.reward_id,
            reward_name=rule.reward_name_snapshot,
            duration_months=rule.duration_months,
            is_permanent=rule.is_permanent,
            enabled=rule.enabled,
            rule_id=rule.id,
        )

        if (
            entitlement is not None
            and entitlement.status is VipEntitlementStatus.ACTIVE
            and entitlement.source is not VipEntitlementSource.MANAGED
        ):
            return VipRedemptionPlan(
                action=VipRedemptionDecision.NEEDS_REVIEW,
                granted_at=redeemed_at,
                expires_at=None,
                is_permanent=False,
            )

        if (
            entitlement is not None
            and entitlement.status is VipEntitlementStatus.ACTIVE
            and entitlement.source is VipEntitlementSource.MANAGED
            and entitlement.is_permanent
        ):
            return VipRedemptionPlan(
                action=VipRedemptionDecision.NOOP_PERMANENT,
                granted_at=entitlement.granted_at or redeemed_at,
                expires_at=None,
                is_permanent=True,
            )

        action = (
            VipRedemptionDecision.EXTEND if entitlement is not None else VipRedemptionDecision.GRANT
        )
        granted_at = (
            entitlement.granted_at if entitlement and entitlement.granted_at else redeemed_at
        )
        if rule.is_permanent:
            return VipRedemptionPlan(
                action=action,
                granted_at=granted_at,
                expires_at=None,
                is_permanent=True,
            )

        assert rule.duration_months is not None
        base = redeemed_at
        if entitlement is not None and entitlement.expires_at is not None:
            base = max(base, entitlement.expires_at)
        return VipRedemptionPlan(
            action=action,
            granted_at=granted_at,
            expires_at=add_calendar_months(base, rule.duration_months),
            is_permanent=False,
        )
