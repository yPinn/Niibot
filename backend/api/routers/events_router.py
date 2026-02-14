"""Event and redemption configuration API routes"""

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import CommandConfigService, EventConfigService, TwitchAPIClient
from services.channel_service import ChannelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


# ============================================
# Response / Request Models
# ============================================


class EventConfigResponse(BaseModel):
    id: int
    channel_id: str
    event_type: str
    message_template: str
    enabled: bool
    options: dict = {}
    trigger_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EventConfigUpdate(BaseModel):
    message_template: str
    enabled: bool
    options: dict | None = None


class EventConfigToggle(BaseModel):
    enabled: bool


class TwitchRewardResponse(BaseModel):
    id: str
    title: str
    cost: int


class RedemptionConfigResponse(BaseModel):
    id: int
    channel_id: str
    action_type: str
    reward_name: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RedemptionConfigUpdate(BaseModel):
    reward_name: str
    enabled: bool


# ============================================
# Event Config Endpoints
# ============================================

VALID_EVENT_TYPES = {"follow", "subscribe", "raid"}


@router.get("/configs", response_model=list[EventConfigResponse])
async def get_event_configs(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[EventConfigResponse]:
    """Get all event configs for the authenticated user's channel."""
    try:
        service = EventConfigService(pool)
        configs = await service.list_configs_with_counts(channel_id)
        return [EventConfigResponse(**cfg) for cfg in configs]
    except Exception as e:
        logger.exception(f"Failed to get event configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch event configs") from None


@router.put("/configs/{event_type}", response_model=EventConfigResponse)
async def update_event_config(
    event_type: str,
    body: EventConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> EventConfigResponse:
    """Update an event config's message template and enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")
    try:
        service = EventConfigService(pool)
        cfg = await service.update_config(
            channel_id, event_type, body.message_template, body.enabled, body.options
        )
        logger.info(f"Channel {channel_id} updated event config: {event_type}")
        return EventConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to update event config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update event config") from None


@router.patch("/configs/{event_type}/toggle", response_model=EventConfigResponse)
async def toggle_event_config(
    event_type: str,
    body: EventConfigToggle,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> EventConfigResponse:
    """Toggle an event config's enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")
    try:
        service = EventConfigService(pool)
        cfg = await service.toggle_config(channel_id, event_type, body.enabled)
        logger.info(f"Channel {channel_id} toggled event config: {event_type} -> {body.enabled}")
        return EventConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to toggle event config: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle event config") from None


# ============================================
# Twitch Rewards Endpoint
# ============================================


@router.get("/twitch-rewards", response_model=list[TwitchRewardResponse])
async def get_twitch_rewards(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[TwitchRewardResponse]:
    """Fetch custom channel point rewards from Twitch API."""
    try:
        channel_svc = ChannelService(pool)
        token = await channel_svc.get_token_with_refresh(channel_id, twitch_api)
        if not token:
            raise HTTPException(status_code=401, detail="No valid Twitch token")

        rewards = await twitch_api.get_custom_rewards(channel_id, token)
        return [TwitchRewardResponse(**r) for r in rewards]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to fetch Twitch rewards: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch Twitch rewards") from None


# ============================================
# Redemption Config Endpoints
# ============================================

VALID_ACTION_TYPES = {"vip", "first", "niibot_auth"}


@router.get("/redemptions", response_model=list[RedemptionConfigResponse])
async def get_redemption_configs(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[RedemptionConfigResponse]:
    """Get all redemption configs for the authenticated user's channel."""
    try:
        service = CommandConfigService(pool)
        configs = await service.list_redemptions(channel_id)
        return [RedemptionConfigResponse(**cfg) for cfg in configs]
    except Exception as e:
        logger.exception(f"Failed to get redemption configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch redemption configs") from None


@router.put("/redemptions/{action_type}", response_model=RedemptionConfigResponse)
async def update_redemption_config(
    action_type: str,
    body: RedemptionConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> RedemptionConfigResponse:
    """Update a redemption config's reward name and enabled state."""
    if action_type not in VALID_ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {action_type}")
    try:
        service = CommandConfigService(pool)
        cfg = await service.update_redemption(
            channel_id, action_type, body.reward_name, body.enabled
        )
        logger.info(f"Channel {channel_id} updated redemption: {action_type}")
        return RedemptionConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to update redemption config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update redemption config") from None
