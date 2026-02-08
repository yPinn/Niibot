"""Event configuration API routes"""

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_user_id, get_db_pool
from services import EventConfigService

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
    trigger_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EventConfigUpdate(BaseModel):
    message_template: str
    enabled: bool


class EventConfigToggle(BaseModel):
    enabled: bool


# ============================================
# Endpoints
# ============================================

VALID_EVENT_TYPES = {"follow", "subscribe", "raid"}


@router.get("/configs", response_model=list[EventConfigResponse])
async def get_event_configs(
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> list[EventConfigResponse]:
    """Get all event configs for the authenticated user's channel."""
    try:
        service = EventConfigService(pool)
        configs = await service.list_configs_with_counts(user_id)
        return [EventConfigResponse(**cfg) for cfg in configs]
    except Exception as e:
        logger.exception(f"Failed to get event configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch event configs") from None


@router.put("/configs/{event_type}", response_model=EventConfigResponse)
async def update_event_config(
    event_type: str,
    body: EventConfigUpdate,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> EventConfigResponse:
    """Update an event config's message template and enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")
    try:
        service = EventConfigService(pool)
        cfg = await service.update_config(user_id, event_type, body.message_template, body.enabled)
        logger.info(f"User {user_id} updated event config: {event_type}")
        return EventConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to update event config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update event config") from None


@router.patch("/configs/{event_type}/toggle", response_model=EventConfigResponse)
async def toggle_event_config(
    event_type: str,
    body: EventConfigToggle,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> EventConfigResponse:
    """Toggle an event config's enabled state."""
    if event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")
    try:
        service = EventConfigService(pool)
        cfg = await service.toggle_config(user_id, event_type, body.enabled)
        logger.info(f"User {user_id} toggled event config: {event_type} -> {body.enabled}")
        return EventConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to toggle event config: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle event config") from None
