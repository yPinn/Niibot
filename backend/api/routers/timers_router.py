"""Timer configuration API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_channel_id, get_db_pool
from services.timer_service import TimerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timers", tags=["timers"])


# ============================================
# Request / Response Models
# ============================================


class TimerConfigResponse(BaseModel):
    id: int
    channel_id: str
    timer_name: str
    interval_seconds: int
    min_lines: int
    message_template: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TimerCreate(BaseModel):
    timer_name: str
    interval_seconds: int
    min_lines: int = 5
    message_template: str


class TimerUpdate(BaseModel):
    interval_seconds: int | None = None
    min_lines: int | None = None
    message_template: str | None = None
    enabled: bool | None = None


class TimerToggle(BaseModel):
    enabled: bool


# ============================================
# Endpoints
# ============================================


@router.get("/configs", response_model=list[TimerConfigResponse])
async def get_timer_configs(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[TimerConfigResponse]:
    """Get all timers for the authenticated user's channel."""
    service = TimerService(pool)
    timers = await service.list_timers(channel_id)
    return [TimerConfigResponse(**t) for t in timers]


@router.post("/configs", response_model=TimerConfigResponse, status_code=201)
async def create_timer(
    body: TimerCreate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> TimerConfigResponse:
    """Create a new timer."""
    service = TimerService(pool)
    try:
        timer = await service.create_timer(
            channel_id,
            body.timer_name,
            interval_seconds=body.interval_seconds,
            min_lines=body.min_lines,
            message_template=body.message_template,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return TimerConfigResponse(**timer)


@router.put("/configs/{timer_name}", response_model=TimerConfigResponse)
async def update_timer(
    timer_name: str,
    body: TimerUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> TimerConfigResponse:
    """Update a timer's settings."""
    service = TimerService(pool)
    try:
        timer = await service.update_timer(
            channel_id,
            timer_name,
            interval_seconds=body.interval_seconds,
            min_lines=body.min_lines,
            message_template=body.message_template,
            enabled=body.enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return TimerConfigResponse(**timer)


@router.patch("/configs/{timer_name}/toggle", response_model=TimerConfigResponse)
async def toggle_timer(
    timer_name: str,
    body: TimerToggle,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> TimerConfigResponse:
    """Toggle a timer's enabled state."""
    service = TimerService(pool)
    timer = await service.toggle_timer(channel_id, timer_name, body.enabled)
    return TimerConfigResponse(**timer)


@router.delete("/configs/{timer_name}", status_code=204)
async def delete_timer(
    timer_name: str,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> None:
    """Delete a timer."""
    service = TimerService(pool)
    deleted = await service.delete_timer(channel_id, timer_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Timer not found")
