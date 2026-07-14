"""Timer configuration API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_channel_id, get_timer_service, require_activated
from services.timer_service import TimerService

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timers", tags=["timers"])


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
    try:
        timers = await service.list_timers(channel_id)
        return [TimerConfigResponse(**t) for t in timers]
    except Exception:
        LOGGER.exception("Failed to get timer configs")
        raise HTTPException(status_code=500, detail="Failed to fetch timer configs") from None


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
        LOGGER.info("Channel %s created timer: %s", channel_id, body.timer_name)
        return TimerConfigResponse(**timer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        LOGGER.exception("Failed to create timer")
        raise HTTPException(status_code=500, detail="Failed to create timer") from None


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
        if timer is None:
            raise HTTPException(status_code=404, detail="Timer not found")
        LOGGER.info("Channel %s updated timer: %s", channel_id, timer_name)
        return TimerConfigResponse(**timer)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        LOGGER.exception("Failed to update timer")
        raise HTTPException(status_code=500, detail="Failed to update timer") from None


@router.patch("/configs/{timer_name}/toggle", response_model=TimerConfigResponse)
async def toggle_timer(
    timer_name: str,
    body: TimerToggle,
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> TimerConfigResponse:
    """Toggle a timer's enabled state."""
    try:
        timer = await service.toggle_timer(channel_id, timer_name, body.enabled)
        if timer is None:
            raise HTTPException(status_code=404, detail="Timer not found")
        LOGGER.info("Channel %s toggled timer: %s -> %s", channel_id, timer_name, body.enabled)
        return TimerConfigResponse(**timer)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to toggle timer")
        raise HTTPException(status_code=500, detail="Failed to toggle timer") from None


@router.delete("/configs/{timer_name}", status_code=204)
async def delete_timer(
    timer_name: str,
    channel_id: str = Depends(get_current_channel_id),
    service: TimerService = Depends(get_timer_service),
    _: None = Depends(require_activated),
) -> None:
    """Delete a timer."""
    try:
        deleted = await service.delete_timer(channel_id, timer_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="Timer not found")
        LOGGER.info("Channel %s deleted timer: %s", channel_id, timer_name)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to delete timer")
        raise HTTPException(status_code=500, detail="Failed to delete timer") from None
