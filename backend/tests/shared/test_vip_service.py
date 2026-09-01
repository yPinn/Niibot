"""Timed VIP domain rules independent from Twitch transport."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models.vip import (
    VipEntitlement,
    VipEntitlementSource,
    VipEntitlementStatus,
    VipRedemptionDecision,
    VipRewardRule,
)
from shared.services.vip import VipService, add_calendar_months


def _rule(*, months: int | None = 3, permanent: bool = False) -> VipRewardRule:
    return VipRewardRule(
        id=1,
        channel_id="ch1",
        reward_id="reward-1",
        reward_name_snapshot="VIP 三個月",
        duration_months=months,
        is_permanent=permanent,
        enabled=True,
    )


def _entitlement(
    *,
    source: VipEntitlementSource = VipEntitlementSource.MANAGED,
    expires_at: datetime | None = datetime(2026, 5, 15, 12, tzinfo=UTC),
    permanent: bool = False,
) -> VipEntitlement:
    return VipEntitlement(
        id=4,
        channel_id="ch1",
        user_id="u1",
        user_login="alice",
        display_name="Alice",
        source=source,
        status=VipEntitlementStatus.ACTIVE,
        granted_at=datetime(2026, 2, 15, 12, tzinfo=UTC),
        expires_at=expires_at,
        is_permanent=permanent,
        last_reward_rule_id=1,
        last_synced_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("value", "months", "expected"),
    [
        (
            datetime(2026, 1, 31, 10, tzinfo=UTC),
            1,
            datetime(2026, 2, 28, 10, tzinfo=UTC),
        ),
        (
            datetime(2028, 1, 31, 10, tzinfo=UTC),
            1,
            datetime(2028, 2, 29, 10, tzinfo=UTC),
        ),
        (
            datetime(2026, 11, 30, 10, tzinfo=UTC),
            3,
            datetime(2027, 2, 28, 10, tzinfo=UTC),
        ),
    ],
)
def test_add_calendar_months_clamps_to_last_valid_day(value, months, expected):
    assert add_calendar_months(value, months) == expected


def test_add_calendar_months_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        add_calendar_months(datetime(2026, 1, 1), 1)


class TestVipService:
    @pytest.mark.asyncio
    async def test_requires_an_active_tenant_scoped_entitlement_before_manual_removal(self):
        repository = MagicMock()
        repository.get_entitlement = AsyncMock(return_value=_entitlement())
        service = VipService(repository)

        entitlement = await service.require_active_entitlement(channel_id="ch1", user_id="u1")

        assert entitlement.user_id == "u1"
        repository.get_entitlement.assert_awaited_once_with(channel_id="ch1", user_id="u1")

    @pytest.mark.asyncio
    async def test_rejects_manual_removal_when_the_entitlement_is_not_active(self):
        repository = MagicMock()
        repository.get_entitlement = AsyncMock(return_value=None)
        service = VipService(repository)

        with pytest.raises(ValueError, match="active VIP entitlement"):
            await service.require_active_entitlement(channel_id="ch1", user_id="u1")

    @pytest.mark.asyncio
    async def test_records_manual_removal_after_twitch_confirms_it(self):
        repository = MagicMock()
        repository.mark_removed_external = AsyncMock()
        service = VipService(repository)
        removed_at = datetime(2026, 9, 1, tzinfo=UTC)

        await service.record_manual_removal(channel_id="ch1", user_id="u1", removed_at=removed_at)

        repository.mark_removed_external.assert_awaited_once_with(
            channel_id="ch1", user_id="u1", synced_at=removed_at
        )

    def test_new_rule_defaults_to_three_months(self):
        rule = VipService.build_rule(
            channel_id="ch1",
            reward_id="reward-1",
            reward_name="VIP",
        )

        assert rule.duration_months == 3
        assert rule.is_permanent is False

    def test_repeat_redemption_extends_from_current_expiry(self):
        redeemed_at = datetime(2026, 4, 1, 12, tzinfo=UTC)

        decision = VipService.plan_redemption(
            entitlement=_entitlement(),
            rule=_rule(),
            redeemed_at=redeemed_at,
        )

        assert decision.action is VipRedemptionDecision.EXTEND
        assert decision.expires_at == datetime(2026, 8, 15, 12, tzinfo=UTC)

    def test_expired_managed_record_extends_from_redemption_time(self):
        redeemed_at = datetime(2026, 7, 1, 12, tzinfo=UTC)

        decision = VipService.plan_redemption(
            entitlement=_entitlement(),
            rule=_rule(),
            redeemed_at=redeemed_at,
        )

        assert decision.expires_at == datetime(2026, 10, 1, 12, tzinfo=UTC)

    def test_external_vip_requires_manual_review(self):
        decision = VipService.plan_redemption(
            entitlement=_entitlement(source=VipEntitlementSource.EXTERNAL_BASELINE),
            rule=_rule(),
            redeemed_at=datetime(2026, 4, 1, tzinfo=UTC),
        )

        assert decision.action is VipRedemptionDecision.NEEDS_REVIEW
        assert decision.expires_at is None

    def test_permanent_entitlement_is_never_shortened(self):
        decision = VipService.plan_redemption(
            entitlement=_entitlement(expires_at=None, permanent=True),
            rule=_rule(months=1),
            redeemed_at=datetime(2026, 4, 1, tzinfo=UTC),
        )

        assert decision.action is VipRedemptionDecision.NOOP_PERMANENT
        assert decision.expires_at is None

    def test_permanent_reward_upgrades_managed_entitlement(self):
        decision = VipService.plan_redemption(
            entitlement=_entitlement(),
            rule=_rule(months=None, permanent=True),
            redeemed_at=datetime(2026, 4, 1, tzinfo=UTC),
        )

        assert decision.action is VipRedemptionDecision.EXTEND
        assert decision.is_permanent is True
        assert decision.expires_at is None

    @pytest.mark.parametrize("months", [0, 121])
    def test_rule_duration_is_bounded(self, months):
        with pytest.raises(ValueError, match="between 1 and 120"):
            VipService.build_rule(
                channel_id="ch1",
                reward_id="reward-1",
                reward_name="VIP",
                duration_months=months,
            )
