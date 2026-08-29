"""Event and redemption configuration API routes"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.dependencies import (
    get_channel_service,
    get_command_config_service,
    get_current_channel_id,
    get_event_config_service,
    get_twitch_api,
)
from services import ChannelService, CommandConfigService, EventConfigService, TwitchAPIClient
from shared.errors import AccessDeniedError, AppError, InvalidInputError, NotFoundError
from shared.events import EVENT_CATALOG
from shared.repositories.event_config import EVENT_TYPES as VALID_EVENT_TYPES

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


class EventConfigNotFoundError(NotFoundError):
    code = "EVENT.NOT_FOUND"
    user_message = "找不到這個事件設定"


class EventInvalidError(InvalidInputError):
    code = "EVENT.INVALID"
    user_message = "事件類型不正確"


class NotAffiliateError(AccessDeniedError):
    code = "EVENT.NOT_AFFILIATE"
    user_message = "頻道還不是 Twitch 會員或合作夥伴"


class NoTwitchTokenError(AppError):
    code = "AUTH.NO_TOKEN"
    http_status = 401
    user_message = "Twitch 授權已失效，請重新登入"


class EventConfigResponse(BaseModel):
    id: int
    channel_id: str
    event_type: str
    message_template: str
    enabled: bool
    options: dict = Field(default_factory=dict)
    # None when the event writes no stream_events row (resub / gift_sub) — the
    # dashboard shows "—" rather than a misleading 0.
    trigger_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EventVariableResponse(BaseModel):
    name: str
    description: str
    sample: str


class EventOptionResponse(BaseModel):
    key: str
    type: str
    label: str
    description: str
    default: bool


class EventDefinitionResponse(BaseModel):
    key: str
    display_name: str
    category_label: str
    accent: str
    requires_affiliate: bool
    default_template: str
    default_enabled: bool
    variables: list[EventVariableResponse]
    options_schema: list[EventOptionResponse]


_CATALOG_PAYLOAD: list[EventDefinitionResponse] = [
    EventDefinitionResponse(
        key=e.key,
        display_name=e.display_name,
        category_label=e.category_label,
        accent=e.accent,
        requires_affiliate=e.requires_affiliate,
        default_template=e.default_template,
        default_enabled=e.default_enabled,
        variables=[
            EventVariableResponse(name=v.name, description=v.description, sample=v.sample)
            for v in e.variables
        ],
        options_schema=[
            EventOptionResponse(
                key=o.key,
                type=o.type,
                label=o.label,
                description=o.description,
                default=o.default,
            )
            for o in e.options_schema
        ],
    )
    for e in EVENT_CATALOG
]


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


@router.get("/catalog", response_model=list[EventDefinitionResponse])
async def get_event_catalog() -> list[EventDefinitionResponse]:
    """Static definition of every configurable event: template variables (with
    preview samples), display metadata, and the per-event options schema.

    Drives the dashboard so it stops hand-mirroring ``shared.events``. Returned
    in display order; the array order *is* the order.
    """
    return _CATALOG_PAYLOAD


@router.get("/configs", response_model=list[EventConfigResponse])
async def get_event_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: EventConfigService = Depends(get_event_config_service),
) -> list[EventConfigResponse]:
    """Get all event configs for the authenticated user's channel."""
    configs = await service.list_configs_with_counts(channel_id)
    return [EventConfigResponse(**cfg) for cfg in configs]


@router.put("/configs/{event_type}", response_model=EventConfigResponse)
async def update_event_config(
    event_type: str,
    body: EventConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: EventConfigService = Depends(get_event_config_service),
) -> EventConfigResponse:
    """Update an event config's message template and enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise EventInvalidError(context={"event_type": event_type})
    cfg = await service.update_config(
        channel_id, event_type, body.message_template, body.enabled, body.options
    )
    if cfg is None:
        raise EventConfigNotFoundError(context={"event_type": event_type})
    LOGGER.info("event_config_updated", extra={"event_type": event_type})
    return EventConfigResponse(**cfg)


@router.patch("/configs/{event_type}/toggle", response_model=EventConfigResponse)
async def toggle_event_config(
    event_type: str,
    body: EventConfigToggle,
    channel_id: str = Depends(get_current_channel_id),
    service: EventConfigService = Depends(get_event_config_service),
) -> EventConfigResponse:
    """Toggle an event config's enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise EventInvalidError(context={"event_type": event_type})
    cfg = await service.toggle_config(channel_id, event_type, body.enabled)
    if cfg is None:
        raise EventConfigNotFoundError(context={"event_type": event_type})
    LOGGER.info("event_config_toggled", extra={"event_type": event_type, "enabled": body.enabled})
    return EventConfigResponse(**cfg)


@router.get("/twitch-rewards", response_model=list[TwitchRewardResponse])
async def get_twitch_rewards(
    channel_id: str = Depends(get_current_channel_id),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[TwitchRewardResponse]:
    """Fetch custom channel point rewards from Twitch API."""
    user_info = await twitch_api.get_user_info(channel_id)
    if not user_info or user_info.get("broadcaster_type") not in ("affiliate", "partner"):
        raise NotAffiliateError()

    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        raise NoTwitchTokenError()

    rewards = await twitch_api.get_custom_rewards(channel_id, token)
    return [TwitchRewardResponse(**r) for r in rewards]


VALID_ACTION_TYPES = {"vip", "first", "niibot_auth", "game_queue", "video_queue"}


@router.get("/redemptions", response_model=list[RedemptionConfigResponse])
async def get_redemption_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> list[RedemptionConfigResponse]:
    """Get all redemption configs for the authenticated user's channel."""
    configs = await service.list_redemptions(channel_id)
    return [RedemptionConfigResponse(**cfg) for cfg in configs]


@router.put("/redemptions/{action_type}", response_model=RedemptionConfigResponse)
async def update_redemption_config(
    action_type: str,
    body: RedemptionConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> RedemptionConfigResponse:
    """Update a redemption config's reward name and enabled state."""
    if action_type not in VALID_ACTION_TYPES:
        raise EventInvalidError(
            user_message="兑換動作類型不正確", context={"action_type": action_type}
        )
    cfg = await service.update_redemption(channel_id, action_type, body.reward_name, body.enabled)
    if cfg is None:
        raise EventConfigNotFoundError(
            user_message="找不到這個兑換設定", context={"action_type": action_type}
        )
    LOGGER.info("redemption_updated", extra={"action_type": action_type})
    return RedemptionConfigResponse(**cfg)
