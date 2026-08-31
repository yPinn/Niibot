"""Timed VIP redemption workflow contracts."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.channel_points import ChannelPointsComponent

from shared.models.vip import (
    VipChannelSettings,
    VipEntitlement,
    VipEntitlementSource,
    VipEntitlementStatus,
    VipRedemptionDecision,
    VipRedemptionEvent,
    VipRedemptionPlan,
    VipRedemptionStatus,
    VipRewardRule,
)

_NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.sessions.session_id.return_value = None
    return bot


def _payload() -> MagicMock:
    payload = MagicMock()
    payload.id = "redemption-1"
    payload.broadcaster.id = "channel-1"
    payload.broadcaster.name = "streamer"
    payload.broadcaster.add_vip = AsyncMock()
    payload.user.id = "viewer-1"
    payload.user.name = "viewer"
    payload.user.display_name = "Viewer"
    payload.reward.id = "reward-vip-3m"
    payload.reward.title = "VIP 三個月"
    payload.reward.cost = 50_000
    payload.user_input = ""
    return payload


def _rule() -> VipRewardRule:
    return VipRewardRule(
        id=2,
        channel_id="channel-1",
        reward_id="reward-vip-3m",
        reward_name_snapshot="VIP 三個月",
        duration_months=3,
        is_permanent=False,
        enabled=True,
    )


def _settings(*, initialized: bool = True, limit: int = 10) -> VipChannelSettings:
    return VipChannelSettings(
        channel_id="channel-1",
        slot_limit=limit,
        tracking_started_at=_NOW if initialized else None,
        last_full_sync_at=_NOW if initialized else None,
    )


def _receipt(status: VipRedemptionStatus = VipRedemptionStatus.RECEIVED):
    return VipRedemptionEvent(
        id=9,
        channel_id="channel-1",
        redemption_id="redemption-1",
        rule_id=2,
        reward_id="reward-vip-3m",
        reward_name_snapshot="VIP 三個月",
        user_id="viewer-1",
        user_login="viewer",
        display_name="Viewer",
        duration_months_snapshot=3,
        is_permanent_snapshot=False,
        status=status,
        error_code=None,
        occurred_at=_NOW,
        processed_at=None,
        created_at=_NOW,
    )


def _component() -> ChannelPointsComponent:
    component = ChannelPointsComponent(_bot())
    component.redemption_repo.find_by_reward = AsyncMock()
    component.vip_repo.get_reward_rule = AsyncMock(return_value=_rule())
    component.vip_repo.record_redemption = AsyncMock(return_value=_receipt())
    component.vip_repo.get_or_create_settings = AsyncMock(return_value=_settings())
    component.vip_repo.reconcile_snapshot = AsyncMock()
    component.vip_repo.get_entitlement = AsyncMock(return_value=None)
    component.vip_repo.count_active = AsyncMock(return_value=0)
    component.vip_repo.apply_managed_entitlement = AsyncMock()
    component.vip_repo.transition_redemption = AsyncMock()
    component._fetch_vip_snapshot = AsyncMock(return_value=())  # type: ignore[method-assign]
    component._reply = AsyncMock()  # type: ignore[method-assign]
    return component


@pytest.mark.asyncio
async def test_vip_rule_is_resolved_before_legacy_single_action_config():
    component = _component()
    component._handle_timed_vip_redemption = AsyncMock()  # type: ignore[method-assign]
    payload = _payload()

    await component._handle_redemption(payload)

    component.vip_repo.get_reward_rule.assert_awaited_once_with(
        channel_id="channel-1", reward_id="reward-vip-3m"
    )
    component._handle_timed_vip_redemption.assert_awaited_once_with(payload, _rule())
    component.redemption_repo.find_by_reward.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_timed_vip_rule_does_not_fall_back_to_legacy_grant():
    component = _component()
    component.vip_repo.get_reward_rule.return_value = replace(_rule(), enabled=False)
    component._handle_timed_vip_redemption = AsyncMock()  # type: ignore[method-assign]

    await component._handle_redemption(_payload())

    component._handle_timed_vip_redemption.assert_not_awaited()
    component.redemption_repo.find_by_reward.assert_not_awaited()


@pytest.mark.asyncio
async def test_uninitialized_tracking_records_failure_without_granting():
    component = _component()
    component.vip_repo.get_or_create_settings.return_value = _settings(initialized=False)
    payload = _payload()

    await component._handle_timed_vip_redemption(payload, _rule())

    payload.broadcaster.add_vip.assert_not_awaited()
    component.vip_repo.transition_redemption.assert_awaited_once_with(
        channel_id="channel-1",
        redemption_id="redemption-1",
        status=VipRedemptionStatus.NOT_INITIALIZED,
        error_code="vip_tracking_not_initialized",
    )
    assert "尚未完成" in component._reply.await_args.args[1]


@pytest.mark.asyncio
async def test_full_manual_capacity_does_not_call_twitch_add():
    component = _component()
    component.vip_repo.count_active.return_value = 10
    payload = _payload()

    await component._handle_timed_vip_redemption(payload, _rule())

    payload.broadcaster.add_vip.assert_not_awaited()
    component.vip_repo.transition_redemption.assert_awaited_once_with(
        channel_id="channel-1",
        redemption_id="redemption-1",
        status=VipRedemptionStatus.CAPACITY_FULL,
        error_code="vip_capacity_full",
    )
    assert "退款" in component._reply.await_args.args[1]


@pytest.mark.asyncio
async def test_new_viewer_is_granted_and_persisted_after_fresh_snapshot():
    component = _component()
    component.vip_policy.plan_redemption = MagicMock(
        return_value=VipRedemptionPlan(
            action=VipRedemptionDecision.GRANT,
            granted_at=_NOW,
            expires_at=datetime(2026, 11, 30, 12, tzinfo=UTC),
            is_permanent=False,
        )
    )
    payload = _payload()

    await component._handle_timed_vip_redemption(payload, _rule())

    component._fetch_vip_snapshot.assert_awaited_once_with(payload.broadcaster)
    component.vip_repo.reconcile_snapshot.assert_awaited_once()
    payload.broadcaster.add_vip.assert_awaited_once_with(user=payload.user)
    component.vip_repo.apply_managed_entitlement.assert_awaited_once()
    assert component.vip_repo.transition_redemption.await_args_list[-1].kwargs == {
        "channel_id": "channel-1",
        "redemption_id": "redemption-1",
        "status": VipRedemptionStatus.GRANTED,
        "error_code": None,
    }
    assert (
        component.vip_repo.transition_redemption.await_args_list[0].kwargs["status"]
        is VipRedemptionStatus.GRANTING
    )


@pytest.mark.asyncio
async def test_external_vip_is_queued_for_manual_review():
    component = _component()
    external = VipEntitlement(
        id=3,
        channel_id="channel-1",
        user_id="viewer-1",
        user_login="viewer",
        display_name="Viewer",
        source=VipEntitlementSource.EXTERNAL_BASELINE,
        status=VipEntitlementStatus.ACTIVE,
        granted_at=None,
        expires_at=None,
        is_permanent=False,
        last_reward_rule_id=None,
        last_synced_at=_NOW,
    )
    component.vip_repo.get_entitlement.return_value = external
    payload = _payload()

    await component._handle_timed_vip_redemption(payload, _rule())

    payload.broadcaster.add_vip.assert_not_awaited()
    component.vip_repo.transition_redemption.assert_awaited_once_with(
        channel_id="channel-1",
        redemption_id="redemption-1",
        status=VipRedemptionStatus.NEEDS_REVIEW_EXTERNAL_VIP,
        error_code="external_vip_requires_review",
    )
    assert "人工確認" in component._reply.await_args.args[1]


@pytest.mark.asyncio
async def test_completed_receipt_is_not_processed_twice_after_restart():
    component = _component()
    component.vip_repo.record_redemption.return_value = _receipt(VipRedemptionStatus.GRANTED)
    payload = _payload()

    await component._handle_timed_vip_redemption(payload, _rule())

    component._fetch_vip_snapshot.assert_not_awaited()
    payload.broadcaster.add_vip.assert_not_awaited()


def _due_entitlement() -> VipEntitlement:
    return VipEntitlement(
        id=22,
        channel_id="channel-1",
        user_id="viewer-1",
        user_login="viewer",
        display_name="Viewer",
        source=VipEntitlementSource.MANAGED,
        status=VipEntitlementStatus.ACTIVE,
        granted_at=datetime(2026, 5, 31, tzinfo=UTC),
        expires_at=_NOW,
        is_permanent=False,
        last_reward_rule_id=2,
        last_synced_at=_NOW,
        expiry_claimed_at=_NOW,
    )


@pytest.mark.asyncio
async def test_expiry_does_not_remove_again_when_twitch_vip_is_already_gone():
    component = _component()
    component.vip_repo.claim_due_entitlements = AsyncMock(return_value=(_due_entitlement(),))
    component.vip_repo.finish_expiry = AsyncMock()
    component.vip_repo.release_expiry_claim = AsyncMock()
    component._is_current_vip = AsyncMock(return_value=False)  # type: ignore[method-assign]
    broadcaster = MagicMock()
    broadcaster.remove_vip = AsyncMock()
    component.bot.create_partialuser.return_value = broadcaster

    await component._expire_due_vips()

    broadcaster.remove_vip.assert_not_awaited()
    component.vip_repo.finish_expiry.assert_awaited_once()
    assert component.vip_repo.finish_expiry.await_args.kwargs["externally_removed"] is True


@pytest.mark.asyncio
async def test_expiry_removes_current_twitch_vip_then_closes_entitlement(monkeypatch):
    component = _component()
    component.vip_repo.claim_due_entitlements = AsyncMock(return_value=(_due_entitlement(),))
    component.vip_repo.finish_expiry = AsyncMock()
    component.vip_repo.release_expiry_claim = AsyncMock()
    component._is_current_vip = AsyncMock(return_value=True)  # type: ignore[method-assign]
    broadcaster = MagicMock()
    broadcaster.remove_vip = AsyncMock()
    viewer = MagicMock()
    component.bot.create_partialuser.side_effect = [broadcaster, viewer]
    sleep = AsyncMock()
    monkeypatch.setattr("twitch.components.channel_points.asyncio.sleep", sleep)

    await component._expire_due_vips()

    broadcaster.remove_vip.assert_awaited_once_with(user=viewer)
    component.vip_repo.finish_expiry.assert_awaited_once()
    assert component.vip_repo.finish_expiry.await_args.kwargs["externally_removed"] is False
    sleep.assert_awaited_once_with(1.05)
