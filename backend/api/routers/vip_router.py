"""Authenticated, tenant-scoped timed VIP management routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from core.dependencies import (
    get_channel_service,
    get_twitch_api,
    get_vip_service,
    require_self_tenant_access,
)
from services import ChannelService, TwitchAPIClient
from services.tenant_service import TenantContext
from shared.errors import AppError, InvalidInputError, NotFoundError
from shared.models.vip import VipSnapshotMember
from shared.services.vip import VipService

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vip", tags=["vip"])


class VipTwitchUnavailableError(AppError):
    code = "VIP.TWITCH_UNAVAILABLE"
    http_status = 503
    user_message = "目前無法完成 Twitch 貴賓名單清點，請稍後再試"


class VipNoTokenError(AppError):
    code = "VIP.NO_TWITCH_TOKEN"
    http_status = 401
    user_message = "Twitch 授權已失效，請重新登入"


class VipRewardNotFoundError(NotFoundError):
    code = "VIP.REWARD_NOT_FOUND"
    user_message = "找不到這個 Twitch 點數獎勵"


class VipReviewInvalidError(InvalidInputError):
    code = "VIP.REVIEW_INVALID"
    user_message = "這筆貴賓待審項目已失效或無法處理"


class VipSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: str
    slot_limit: int | None
    tracking_started_at: datetime | None
    last_full_sync_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VipRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None
    channel_id: str
    reward_id: str
    reward_name_snapshot: str
    duration_months: int | None
    is_permanent: bool
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VipEntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: str
    user_id: str
    user_login: str
    display_name: str | None
    source: str
    status: str
    granted_at: datetime | None
    expires_at: datetime | None
    is_permanent: bool
    last_reward_rule_id: int | None
    last_synced_at: datetime


class VipRedemptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    redemption_id: str
    reward_id: str
    reward_name_snapshot: str
    user_id: str
    user_login: str
    display_name: str | None
    duration_months_snapshot: int | None
    is_permanent_snapshot: bool
    status: str
    error_code: str | None
    occurred_at: datetime
    processed_at: datetime | None


class VipStateResponse(BaseModel):
    settings: VipSettingsResponse
    rules: list[VipRuleResponse]
    entitlements: list[VipEntitlementResponse]
    redemptions: list[VipRedemptionResponse]


class VipSlotLimitBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    slot_limit: int = Field(ge=1, le=500)


class VipRuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    duration_months: int | None = Field(default=3, ge=1, le=120)
    is_permanent: bool = False
    enabled: bool = True


class VipRulesEnabledBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool


class VipAdoptBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    duration_months: int | None = Field(default=None, ge=1, le=120)
    is_permanent: bool = False


async def _token(
    channel_id: str,
    channel_service: ChannelService,
    twitch_api: TwitchAPIClient,
) -> str:
    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        raise VipNoTokenError()
    return token


@router.get("/state", response_model=VipStateResponse)
async def get_vip_state(
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
) -> VipStateResponse:
    state = await service.get_state(tenant.channel_id)
    return VipStateResponse(
        settings=VipSettingsResponse.model_validate(state.settings),
        rules=[VipRuleResponse.model_validate(rule) for rule in state.rules],
        entitlements=[
            VipEntitlementResponse.model_validate(entitlement) for entitlement in state.entitlements
        ],
        redemptions=[
            VipRedemptionResponse.model_validate(redemption) for redemption in state.redemptions
        ],
    )


@router.patch("/settings", response_model=VipSettingsResponse)
async def update_vip_settings(
    body: VipSlotLimitBody,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
) -> VipSettingsResponse:
    settings = await service.update_slot_limit(
        channel_id=tenant.channel_id, slot_limit=body.slot_limit
    )
    return VipSettingsResponse.model_validate(settings)


@router.post("/initialize", response_model=VipSettingsResponse)
async def initialize_vip_tracking(
    body: VipSlotLimitBody,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> VipSettingsResponse:
    token = await _token(tenant.channel_id, channel_service, twitch_api)
    try:
        rows = await twitch_api.get_vips(tenant.channel_id, token)
    except Exception:
        LOGGER.warning("vip_initial_snapshot_failed")
        raise VipTwitchUnavailableError() from None

    members = tuple(
        VipSnapshotMember(
            user_id=str(row["user_id"]),
            user_login=str(row.get("user_login") or row["user_id"]),
            display_name=row.get("user_name") or None,
        )
        for row in rows
    )
    settings = await service.initialize(
        channel_id=tenant.channel_id,
        slot_limit=body.slot_limit,
        members=members,
        synced_at=datetime.now(UTC),
    )
    LOGGER.info("vip_tracking_initialized", extra={"member_count": len(members)})
    return VipSettingsResponse.model_validate(settings)


@router.post("/sync", status_code=204)
async def sync_vip_state(
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> None:
    token = await _token(tenant.channel_id, channel_service, twitch_api)
    try:
        rows = await twitch_api.get_vips(tenant.channel_id, token)
    except Exception:
        LOGGER.warning("vip_manual_snapshot_failed")
        raise VipTwitchUnavailableError() from None
    members = tuple(
        VipSnapshotMember(
            user_id=str(row["user_id"]),
            user_login=str(row.get("user_login") or row["user_id"]),
            display_name=row.get("user_name") or None,
        )
        for row in rows
    )
    try:
        await service.reconcile(
            channel_id=tenant.channel_id,
            members=members,
            synced_at=datetime.now(UTC),
        )
    except ValueError:
        raise VipReviewInvalidError() from None
    LOGGER.info("vip_state_synced", extra={"member_count": len(members)})


@router.put("/rules/{reward_id}", response_model=VipRuleResponse)
async def upsert_vip_rule(
    reward_id: str,
    body: VipRuleBody,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> VipRuleResponse:
    token = await _token(tenant.channel_id, channel_service, twitch_api)
    rewards = await twitch_api.get_custom_rewards(tenant.channel_id, token)
    reward = next((item for item in rewards if str(item.get("id")) == reward_id), None)
    if reward is None:
        raise VipRewardNotFoundError()
    rule = await service.upsert_rule(
        channel_id=tenant.channel_id,
        reward_id=reward_id,
        reward_name=str(reward.get("title") or reward_id),
        duration_months=None if body.is_permanent else body.duration_months,
        is_permanent=body.is_permanent,
        enabled=body.enabled,
    )
    LOGGER.info("vip_reward_rule_upserted", extra={"reward_id": reward_id})
    return VipRuleResponse.model_validate(rule)


@router.patch("/rules/enabled", response_model=list[VipRuleResponse])
async def set_vip_rules_enabled(
    body: VipRulesEnabledBody,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
) -> list[VipRuleResponse]:
    rules = await service.set_rules_enabled(channel_id=tenant.channel_id, enabled=body.enabled)
    LOGGER.info("vip_reward_rules_toggled", extra={"enabled": body.enabled})
    return [VipRuleResponse.model_validate(rule) for rule in rules]


@router.post("/reviews/{redemption_id}/adopt", response_model=VipEntitlementResponse)
async def adopt_external_vip(
    redemption_id: str,
    body: VipAdoptBody,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
) -> VipEntitlementResponse:
    if body.is_permanent and body.duration_months is not None:
        raise VipReviewInvalidError()
    try:
        entitlement = await service.adopt_external_redemption(
            channel_id=tenant.channel_id,
            redemption_id=redemption_id,
            adopted_at=datetime.now(UTC),
            duration_months=body.duration_months,
            is_permanent=body.is_permanent,
        )
    except ValueError:
        raise VipReviewInvalidError() from None
    LOGGER.info("external_vip_adopted", extra={"redemption_id": redemption_id})
    return VipEntitlementResponse.model_validate(entitlement)


@router.post("/reviews/{redemption_id}/keep-external", status_code=204)
async def keep_external_vip(
    redemption_id: str,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
) -> None:
    try:
        await service.keep_external_redemption(
            channel_id=tenant.channel_id, redemption_id=redemption_id
        )
    except ValueError:
        raise VipReviewInvalidError() from None
    LOGGER.info("external_vip_kept", extra={"redemption_id": redemption_id})


@router.patch("/entitlements/{user_id}", response_model=VipEntitlementResponse)
async def adjust_vip_entitlement(
    user_id: str,
    body: VipAdoptBody,
    _action: Literal["vip-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: VipService = Depends(get_vip_service),
) -> VipEntitlementResponse:
    if body.is_permanent and body.duration_months is not None:
        raise VipReviewInvalidError()
    if not body.is_permanent and body.duration_months is None:
        raise VipReviewInvalidError()
    try:
        entitlement = await service.adjust_entitlement(
            channel_id=tenant.channel_id,
            user_id=user_id,
            adjusted_at=datetime.now(UTC),
            duration_months=body.duration_months,
            is_permanent=body.is_permanent,
        )
    except ValueError:
        raise VipReviewInvalidError() from None
    LOGGER.info("managed_vip_adjusted", extra={"user_id": user_id})
    return VipEntitlementResponse.model_validate(entitlement)
