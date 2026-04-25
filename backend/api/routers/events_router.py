"""Event and redemption configuration API routes"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import (
    get_channel_service,
    get_command_config_service,
    get_current_channel_id,
    get_event_config_service,
    get_twitch_api,
)
from services import ChannelService, CommandConfigService, EventConfigService, TwitchAPIClient

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


class EventConfigResponse(BaseModel):
    id: int
    channel_id: str
    event_type: str
    message_template: str
    enabled: bool
    options: dict = Field(default_factory=dict)
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


VALID_EVENT_TYPES = {"follow", "subscribe", "raid", "bits"}


@router.get("/configs", response_model=list[EventConfigResponse])
async def get_event_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: EventConfigService = Depends(get_event_config_service),
) -> list[EventConfigResponse]:
    """Get all event configs for the authenticated user's channel."""
    try:
        configs = await service.list_configs_with_counts(channel_id)
        return [EventConfigResponse(**cfg) for cfg in configs]
    except Exception:
        LOGGER.exception("Failed to get event configs")
        raise HTTPException(status_code=500, detail="Failed to fetch event configs") from None


@router.put("/configs/{event_type}", response_model=EventConfigResponse)
async def update_event_config(
    event_type: str,
    body: EventConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: EventConfigService = Depends(get_event_config_service),
) -> EventConfigResponse:
    """Update an event config's message template and enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")
    try:
        cfg = await service.update_config(
            channel_id, event_type, body.message_template, body.enabled, body.options
        )
        if cfg is None:
            raise HTTPException(status_code=404, detail="Event config not found")
        LOGGER.info(f"Channel {channel_id} updated event config: {event_type}")
        return EventConfigResponse(**cfg)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to update event config")
        raise HTTPException(status_code=500, detail="Failed to update event config") from None


@router.patch("/configs/{event_type}/toggle", response_model=EventConfigResponse)
async def toggle_event_config(
    event_type: str,
    body: EventConfigToggle,
    channel_id: str = Depends(get_current_channel_id),
    service: EventConfigService = Depends(get_event_config_service),
) -> EventConfigResponse:
    """Toggle an event config's enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")
    try:
        cfg = await service.toggle_config(channel_id, event_type, body.enabled)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Event config not found")
        LOGGER.info(f"Channel {channel_id} toggled event config: {event_type} -> {body.enabled}")
        return EventConfigResponse(**cfg)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to toggle event config")
        raise HTTPException(status_code=500, detail="Failed to toggle event config") from None


@router.get("/twitch-rewards", response_model=list[TwitchRewardResponse])
async def get_twitch_rewards(
    channel_id: str = Depends(get_current_channel_id),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[TwitchRewardResponse]:
    """Fetch custom channel point rewards from Twitch API."""
    try:
        user_info = await twitch_api.get_user_info(channel_id)
        if not user_info or user_info.get("broadcaster_type") not in ("affiliate", "partner"):
            raise HTTPException(status_code=403, detail="Channel is not an affiliate or partner")

        token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
        if not token:
            raise HTTPException(status_code=401, detail="No valid Twitch token")

        rewards = await twitch_api.get_custom_rewards(channel_id, token)
        return [TwitchRewardResponse(**r) for r in rewards]
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to fetch Twitch rewards")
        raise HTTPException(status_code=500, detail="Failed to fetch Twitch rewards") from None


VALID_ACTION_TYPES = {"vip", "first", "niibot_auth", "game_queue", "video_queue"}


@router.get("/redemptions", response_model=list[RedemptionConfigResponse])
async def get_redemption_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> list[RedemptionConfigResponse]:
    """Get all redemption configs for the authenticated user's channel."""
    try:
        configs = await service.list_redemptions(channel_id)
        return [RedemptionConfigResponse(**cfg) for cfg in configs]
    except Exception:
        LOGGER.exception("Failed to get redemption configs")
        raise HTTPException(status_code=500, detail="Failed to fetch redemption configs") from None


@router.put("/redemptions/{action_type}", response_model=RedemptionConfigResponse)
async def update_redemption_config(
    action_type: str,
    body: RedemptionConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> RedemptionConfigResponse:
    """Update a redemption config's reward name and enabled state."""
    if action_type not in VALID_ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {action_type}")
    try:
        cfg = await service.update_redemption(
            channel_id, action_type, body.reward_name, body.enabled
        )
        if cfg is None:
            raise HTTPException(status_code=404, detail="Redemption config not found")
        LOGGER.info(f"Channel {channel_id} updated redemption: {action_type}")
        return RedemptionConfigResponse(**cfg)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to update redemption config")
        raise HTTPException(status_code=500, detail="Failed to update redemption config") from None
