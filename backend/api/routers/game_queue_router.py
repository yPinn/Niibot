"""Game queue API routes."""

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import TwitchAPIClient
from services.game_queue_service import GameQueueService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/game-queue", tags=["game-queue"])


# ============================================
# Response / Request Models
# ============================================


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


# ============================================
# Queue State Endpoints
# ============================================


@router.get("/state", response_model=QueueStateResponse)
async def get_queue_state(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> QueueStateResponse:
    """Get full queue state for the authenticated user's channel."""
    try:
        service = GameQueueService(pool)
        state = await service.get_queue_state(channel_id)
        return QueueStateResponse(**state)
    except Exception as e:
        logger.exception(f"Failed to get queue state: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None


@router.post("/advance", response_model=QueueStateResponse)
async def advance_batch(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> QueueStateResponse:
    """Complete the current batch and advance to the next."""
    try:
        service = GameQueueService(pool)
        state = await service.advance_batch(channel_id)
        logger.info(f"Channel {channel_id} advanced game queue batch")
        return QueueStateResponse(**state)
    except Exception as e:
        logger.exception(f"Failed to advance batch: {e}")
        raise HTTPException(status_code=500, detail="Failed to advance batch") from None


@router.delete("/entries/{entry_id}", response_model=QueueStateResponse)
async def remove_player(
    entry_id: int,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> QueueStateResponse:
    """Remove a specific player from the queue."""
    try:
        service = GameQueueService(pool)
        state = await service.remove_player(channel_id, entry_id)
        logger.info(f"Channel {channel_id} removed queue entry {entry_id}")
        return QueueStateResponse(**state)
    except Exception as e:
        logger.exception(f"Failed to remove player: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove player") from None


@router.delete("/clear", response_model=ClearResponse)
async def clear_queue(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ClearResponse:
    """Clear entire queue."""
    try:
        service = GameQueueService(pool)
        state = await service.clear_queue(channel_id)
        logger.info(f"Channel {channel_id} cleared game queue")
        return ClearResponse(**state)
    except Exception as e:
        logger.exception(f"Failed to clear queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear queue") from None


# ============================================
# Settings Endpoints
# ============================================


@router.get("/settings", response_model=QueueSettingsResponse)
async def get_settings(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> QueueSettingsResponse:
    """Get queue settings."""
    try:
        service = GameQueueService(pool)
        settings = await service.get_settings(channel_id)
        return QueueSettingsResponse(**settings)
    except Exception as e:
        logger.exception(f"Failed to get queue settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch queue settings") from None


@router.put("/settings", response_model=QueueSettingsResponse)
async def update_settings(
    body: QueueSettingsUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> QueueSettingsResponse:
    """Update queue settings (group_size, enabled)."""
    if body.group_size is None and body.enabled is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        service = GameQueueService(pool)
        settings = await service.update_settings(
            channel_id, group_size=body.group_size, enabled=body.enabled
        )
        logger.info(f"Channel {channel_id} updated queue settings")
        return QueueSettingsResponse(**settings)
    except Exception as e:
        logger.exception(f"Failed to update queue settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update queue settings") from None


# ============================================
# Public Endpoint (OBS Overlay)
# ============================================


@router.get("/public/{username}", response_model=PublicQueueStateResponse)
async def get_public_queue_state(
    username: str,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicQueueStateResponse:
    """Get queue state for OBS overlay (no auth required)."""
    try:
        user_info = await twitch_api.get_user_by_login(username)
        if not user_info:
            raise HTTPException(status_code=404, detail="Channel not found")
        channel_id = user_info["id"]
        service = GameQueueService(pool)
        state = await service.get_public_state(channel_id)
        return PublicQueueStateResponse(**state)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get public queue state: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None
