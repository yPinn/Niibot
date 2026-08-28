"""Timer configuration API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.dependencies import get_current_channel_id, get_timer_service, require_activated
from services.timer_service import TimerService
from shared.errors import InvalidInputError, NotFoundError

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timers", tags=["timers"])


class TimerNotFoundError(NotFoundError):
    code = "TIMER.NOT_FOUND"
    user_message = "找不到這個計時器"


class TimerInvalidError(InvalidInputError):
    code = "TIMER.INVALID"
    user_message = "計時器的設定有誤，請檢查後再試"


class TimerConfigResponse(BaseModel):
    id: int | None
    channel_id: str
    timer_name: str
    interval_seconds: int
    min_lines: int
    message_template: str
    enabled: bool
    announce: bool = False
    command_alias: str | None = None
    builtin: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TimerCreate(BaseModel):
    timer_name: str
    interval_seconds: int = Field(ge=60, le=86400)
    min_lines: int = Field(default=5, ge=0)
    message_template: str
    announce: bool = False
    command_alias: str | None = None


class TimerUpdate(BaseModel):
    interval_seconds: int | None = None
    min_lines: int | None = None
    message_template: str | None = None
    enabled: bool | None = None
    announce: bool | None = None
    command_alias: str | None = None
    clear_alias: bool = False


class TimerToggle(BaseModel):
    enabled: bool


@router.get("/configs", response_model=list[TimerConfigResponse])
async def get_timer_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> list[TimerConfigResponse]:
    """Get all timers for the authenticated user's channel."""
    timers = await service.list_timers(channel_id)
    return [TimerConfigResponse(**t) for t in timers]


@router.post("/configs", response_model=TimerConfigResponse, status_code=201)
async def create_timer(
    body: TimerCreate,
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> TimerConfigResponse:
    """Create a new timer."""
    try:
        timer = await service.create_timer(
            channel_id,
            body.timer_name,
            interval_seconds=body.interval_seconds,
            min_lines=body.min_lines,
            message_template=body.message_template,
            announce=body.announce,
            command_alias=body.command_alias,
        )
    except ValueError as e:
        raise TimerInvalidError(context={"reason": str(e)}) from e
    LOGGER.info("timer_created", extra={"timer_name": body.timer_name})
    return TimerConfigResponse(**timer)


@router.put("/configs/{timer_name}", response_model=TimerConfigResponse)
async def update_timer(
    timer_name: str,
    body: TimerUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> TimerConfigResponse:
    """Update a timer's settings."""
    try:
        timer = await service.update_timer(
            channel_id,
            timer_name,
            interval_seconds=body.interval_seconds,
            min_lines=body.min_lines,
            message_template=body.message_template,
            enabled=body.enabled,
            announce=body.announce,
            command_alias=body.command_alias,
            clear_alias=body.clear_alias,
        )
    except ValueError as e:
        raise TimerInvalidError(context={"reason": str(e)}) from e
    if timer is None:
        raise TimerNotFoundError(context={"timer_name": timer_name})
    LOGGER.info("timer_updated", extra={"timer_name": timer_name})
    return TimerConfigResponse(**timer)


@router.patch("/configs/{timer_name}/toggle", response_model=TimerConfigResponse)
async def toggle_timer(
    timer_name: str,
    body: TimerToggle,
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> TimerConfigResponse:
    """Toggle a timer's enabled state."""
    timer = await service.toggle_timer(channel_id, timer_name, body.enabled)
    if timer is None:
        raise TimerNotFoundError(context={"timer_name": timer_name})
    LOGGER.info("timer_toggled", extra={"timer_name": timer_name, "enabled": body.enabled})
    return TimerConfigResponse(**timer)


@router.delete("/configs/{timer_name}", status_code=204)
async def delete_timer(
    timer_name: str,
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> None:
    """Delete a timer."""
    deleted = await service.delete_timer(channel_id, timer_name)
    if not deleted:
        raise TimerNotFoundError(context={"timer_name": timer_name})
    LOGGER.info("timer_deleted", extra={"timer_name": timer_name})
