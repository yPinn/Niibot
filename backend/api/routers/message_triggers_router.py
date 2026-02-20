"""Message trigger configuration API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_channel_id, get_db_pool
from services.message_trigger_service import MessageTriggerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


# ============================================
# Request / Response Models
# ============================================


class MessageTriggerResponse(BaseModel):
    id: int
    channel_id: str
    trigger_name: str
    match_type: str
    pattern: str
    case_sensitive: bool
    response: str
    min_role: str
    cooldown: int | None
    priority: int
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TriggerCreate(BaseModel):
    trigger_name: str
    match_type: str = "contains"
    pattern: str
    case_sensitive: bool = False
    response: str
    min_role: str = "everyone"
    cooldown: int | None = None
    priority: int = 0


class TriggerUpdate(BaseModel):
    match_type: str | None = None
    pattern: str | None = None
    case_sensitive: bool | None = None
    response: str | None = None
    min_role: str | None = None
    cooldown: int | None = None
    priority: int | None = None
    enabled: bool | None = None


class TriggerToggle(BaseModel):
    enabled: bool


# ============================================
# Endpoints
# ============================================


@router.get("/configs", response_model=list[MessageTriggerResponse])
async def get_trigger_configs(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[MessageTriggerResponse]:
    """Get all message triggers for the authenticated user's channel."""
    service = MessageTriggerService(pool)
    triggers = await service.list_triggers(channel_id)
    return [MessageTriggerResponse(**t) for t in triggers]


@router.post("/configs", response_model=MessageTriggerResponse, status_code=201)
async def create_trigger(
    body: TriggerCreate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> MessageTriggerResponse:
    """Create a new message trigger."""
    service = MessageTriggerService(pool)
    try:
        trigger = await service.create_trigger(
            channel_id,
            body.trigger_name,
            match_type=body.match_type,
            pattern=body.pattern,
            case_sensitive=body.case_sensitive,
            response=body.response,
            min_role=body.min_role,
            cooldown=body.cooldown,
            priority=body.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MessageTriggerResponse(**trigger)


@router.put("/configs/{trigger_name}", response_model=MessageTriggerResponse)
async def update_trigger(
    trigger_name: str,
    body: TriggerUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> MessageTriggerResponse:
    """Update a message trigger's settings."""
    service = MessageTriggerService(pool)
    try:
        trigger = await service.update_trigger(
            channel_id,
            trigger_name,
            match_type=body.match_type,
            pattern=body.pattern,
            case_sensitive=body.case_sensitive,
            response=body.response,
            min_role=body.min_role,
            cooldown=body.cooldown,
            priority=body.priority,
            enabled=body.enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MessageTriggerResponse(**trigger)


@router.patch("/configs/{trigger_name}/toggle", response_model=MessageTriggerResponse)
async def toggle_trigger(
    trigger_name: str,
    body: TriggerToggle,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> MessageTriggerResponse:
    """Toggle a trigger's enabled state."""
    service = MessageTriggerService(pool)
    trigger = await service.toggle_trigger(channel_id, trigger_name, body.enabled)
    return MessageTriggerResponse(**trigger)


@router.delete("/configs/{trigger_name}", status_code=204)
async def delete_trigger(
    trigger_name: str,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> None:
    """Delete a message trigger."""
    service = MessageTriggerService(pool)
    deleted = await service.delete_trigger(channel_id, trigger_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
