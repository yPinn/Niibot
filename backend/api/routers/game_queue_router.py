"""Game queue API routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import (
    get_current_channel_id,
    get_game_queue_service,
    get_twitch_api,
    require_activated,
)
from services import TwitchAPIClient
from services.game_queue_service import GameQueueService

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/game-queue", tags=["game-queue"])


class QueueEntryResponse(BaseModel):
    id: int
    channel_id: str
    user_id: str
    user_name: str
    redeemed_at: datetime
    position: int = 0
    batch: int = 0


class QueueStateResponse(BaseModel):
    current_batch: list[QueueEntryResponse]
    next_batch: list[QueueEntryResponse]
    full_queue: list[QueueEntryResponse]
    group_size: int
    enabled: bool
    total_active: int


class PublicQueueStateResponse(BaseModel):
    current_batch: list[QueueEntryResponse]
    next_batch: list[QueueEntryResponse]
    group_size: int
    enabled: bool
    total_active: int


class QueueSettingsResponse(BaseModel):
    id: int
    channel_id: str
    group_size: int
    enabled: bool


class QueueSettingsUpdate(BaseModel):
    group_size: int | None = Field(default=None, ge=1, le=50)
    enabled: bool | None = None


class ClearResponse(BaseModel):
    current_batch: list[QueueEntryResponse]
    next_batch: list[QueueEntryResponse]
    full_queue: list[QueueEntryResponse]
    group_size: int
    enabled: bool
    total_active: int
    cleared_count: int


@router.get("/state", response_model=QueueStateResponse)
async def get_queue_state(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> QueueStateResponse:
    """Get full queue state for the authenticated user's channel."""
    try:
        state = await service.get_queue_state(channel_id)
        return QueueStateResponse(**state)
    except Exception:
        LOGGER.exception("Failed to get queue state")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None


@router.post("/advance", response_model=QueueStateResponse)
async def advance_batch(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> QueueStateResponse:
    """Complete the current batch and advance to the next."""
    try:
        state = await service.advance_batch(channel_id)
        LOGGER.info("Channel %s advanced game queue batch", channel_id)
        return QueueStateResponse(**state)
    except Exception:
        LOGGER.exception("Failed to advance batch")
        raise HTTPException(status_code=500, detail="Failed to advance batch") from None


@router.delete("/entries/{entry_id}", response_model=QueueStateResponse)
async def remove_player(
    entry_id: int,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> QueueStateResponse:
    """Remove a specific player from the queue."""
    try:
        state = await service.remove_player(channel_id, entry_id)
        LOGGER.info("Channel %s removed queue entry %d", channel_id, entry_id)
        return QueueStateResponse(**state)
    except Exception:
        LOGGER.exception("Failed to remove player")
        raise HTTPException(status_code=500, detail="Failed to remove player") from None


@router.post("/entries/{entry_id}/promote", response_model=QueueStateResponse)
async def promote_player(
    entry_id: int,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> QueueStateResponse:
    """Move a player from the waiting area to the front of the current batch."""
    try:
        state = await service.promote_player(channel_id, entry_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Entry not found or already removed")
        LOGGER.info("Channel %s promoted queue entry %d", channel_id, entry_id)
        return QueueStateResponse(**state)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to promote player")
        raise HTTPException(status_code=500, detail="Failed to promote player") from None


@router.delete("/clear", response_model=ClearResponse)
async def clear_queue(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> ClearResponse:
    """Clear entire queue."""
    try:
        state = await service.clear_queue(channel_id)
        LOGGER.info("Channel %s cleared game queue", channel_id)
        return ClearResponse(**state)
    except Exception:
        LOGGER.exception("Failed to clear queue")
        raise HTTPException(status_code=500, detail="Failed to clear queue") from None


@router.get("/settings", response_model=QueueSettingsResponse)
async def get_settings(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> QueueSettingsResponse:
    """Get queue settings."""
    try:
        settings = await service.get_settings(channel_id)
        return QueueSettingsResponse(**settings)
    except Exception:
        LOGGER.exception("Failed to get queue settings")
        raise HTTPException(status_code=500, detail="Failed to fetch queue settings") from None


@router.put("/settings", response_model=QueueSettingsResponse)
async def update_settings(
    body: QueueSettingsUpdate,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: GameQueueService = Depends(get_game_queue_service),
) -> QueueSettingsResponse:
    """Update queue settings (group_size, enabled)."""
    if body.group_size is None and body.enabled is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        settings = await service.update_settings(
            channel_id, group_size=body.group_size, enabled=body.enabled
        )
        LOGGER.info("Channel %s updated queue settings", channel_id)
        return QueueSettingsResponse(**settings)
    except Exception:
        LOGGER.exception("Failed to update queue settings")
        raise HTTPException(status_code=500, detail="Failed to update queue settings") from None


@router.get("/public/{username}", response_model=PublicQueueStateResponse)
async def get_public_queue_state(
    username: str,
    service: GameQueueService = Depends(get_game_queue_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicQueueStateResponse:
    """Get queue state for OBS overlay (no auth required)."""
    try:
        user_info = await twitch_api.get_user_by_login(username)
        if not user_info:
            raise HTTPException(status_code=404, detail="Channel not found")
        channel_id = user_info["id"]
        state = await service.get_public_state(channel_id)
        return PublicQueueStateResponse(**state)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to get public queue state")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None
