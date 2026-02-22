"""Video queue API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import TwitchAPIClient
from shared.repositories.video_queue import VideoQueueRepository, VideoQueueSettingsRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-queue", tags=["video-queue"])


# ============================================
# Response / Request Models
# ============================================


class VideoEntryResponse(BaseModel):
    id: int
    video_id: str
    title: str | None
    duration_seconds: int | None
    requested_by: str
    started_at: datetime | None


class PublicVideoQueueState(BaseModel):
    enabled: bool
    current: VideoEntryResponse | None
    queue: list[VideoEntryResponse]
    queue_size: int
    total_queued_duration: int | None  # sum of queued entries' duration_seconds (if all known)


class VideoQueueSettingsResponse(BaseModel):
    channel_id: str
    enabled: bool
    min_role_chat: str
    max_duration_seconds: int
    max_queue_size: int


class VideoQueueSettingsUpdate(BaseModel):
    enabled: bool | None = None
    min_role_chat: str | None = Field(
        default=None, pattern="^(everyone|subscriber|vip|moderator|broadcaster)$"
    )
    max_duration_seconds: int | None = Field(default=None, ge=30, le=10800)
    max_queue_size: int | None = Field(default=None, ge=1, le=100)


class AdvanceRequest(BaseModel):
    done_id: int | None = None  # None = kickstart (no video finished, just start first queued)


class MetadataUpdate(BaseModel):
    duration_seconds: int = Field(..., ge=1)


# ============================================
# Helpers
# ============================================


async def _resolve_channel_id(username: str, twitch_api: TwitchAPIClient) -> str:
    user_info = await twitch_api.get_user_by_login(username)
    if not user_info:
        raise HTTPException(status_code=404, detail="Channel not found")
    return user_info["id"]


async def _build_public_state(
    channel_id: str,
    repo: VideoQueueRepository,
    settings_repo: VideoQueueSettingsRepository,
) -> PublicVideoQueueState:
    settings = await settings_repo.get_or_create(channel_id)
    current = await repo.get_current(channel_id)
    queued = await repo.get_queued(channel_id)

    durations = [e.duration_seconds for e in queued]
    total_queued_duration: int | None = None
    if durations and all(d is not None for d in durations):
        total_queued_duration = sum(d for d in durations if d is not None)

    return PublicVideoQueueState(
        enabled=settings.enabled,
        current=VideoEntryResponse(
            id=current.id,
            video_id=current.video_id,
            title=current.title,
            duration_seconds=current.duration_seconds,
            requested_by=current.requested_by,
            started_at=current.started_at,
        )
        if current
        else None,
        queue=[
            VideoEntryResponse(
                id=e.id,
                video_id=e.video_id,
                title=e.title,
                duration_seconds=e.duration_seconds,
                requested_by=e.requested_by,
                started_at=e.started_at,
            )
            for e in queued
        ],
        queue_size=len(queued),
        total_queued_duration=total_queued_duration,
    )


# ============================================
# Public Endpoints (OBS Overlay — no auth)
# ============================================


@router.get("/public/{username}", response_model=PublicVideoQueueState)
async def get_public_state(
    username: str,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicVideoQueueState:
    """Overlay polling endpoint — returns current + queued videos."""
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get public video queue state: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None


@router.post("/public/{username}/advance", response_model=PublicVideoQueueState)
async def advance_queue(
    username: str,
    body: AdvanceRequest,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicVideoQueueState:
    """Called by the overlay when a video ends (or to kickstart an empty current slot).

    If done_id is provided, marks that entry as done.
    Then, if no entry is currently playing, promotes the next queued entry.
    """
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)

        if body.done_id:
            await repo.mark_done(body.done_id)

        # Only promote if there is no entry currently playing (avoid double-play)
        current = await repo.get_current(channel_id)
        if current is None:
            queued = await repo.get_queued(channel_id)
            if queued:
                await repo.set_playing(queued[0].id)

        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to advance video queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to advance queue") from None


@router.patch("/public/{username}/entries/{entry_id}/metadata", status_code=204)
async def update_entry_metadata(
    username: str,
    entry_id: int,
    body: MetadataUpdate,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> None:
    """Overlay reports duration after the YouTube player loads (fallback for API misses)."""
    try:
        await _resolve_channel_id(username, twitch_api)  # validates channel exists
        repo = VideoQueueRepository(pool)
        await repo.update_duration(entry_id, body.duration_seconds)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update video queue metadata: {e}")
        raise HTTPException(status_code=500, detail="Failed to update metadata") from None


# ============================================
# Authenticated Endpoints (Dashboard)
# ============================================


@router.delete("/skip", status_code=200, response_model=PublicVideoQueueState)
async def skip_current(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Skip the currently playing video."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        current = await repo.get_current(channel_id)
        if current:
            await repo.mark_skipped(current.id)
        queued = await repo.get_queued(channel_id)
        if queued:
            await repo.set_playing(queued[0].id)
        logger.info(f"Channel {channel_id} skipped video queue entry")
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception as e:
        logger.exception(f"Failed to skip video: {e}")
        raise HTTPException(status_code=500, detail="Failed to skip video") from None


@router.delete("/clear", status_code=200, response_model=PublicVideoQueueState)
async def clear_queue(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Clear the entire queue (current + all queued)."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        current = await repo.get_current(channel_id)
        if current:
            await repo.mark_skipped(current.id)
        await repo.clear_queued(channel_id)
        logger.info(f"Channel {channel_id} cleared video queue")
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception as e:
        logger.exception(f"Failed to clear video queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear queue") from None


@router.get("/settings", response_model=VideoQueueSettingsResponse)
async def get_settings(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueSettingsResponse:
    """Get video queue settings."""
    try:
        settings_repo = VideoQueueSettingsRepository(pool)
        s = await settings_repo.get_or_create(channel_id)
        return VideoQueueSettingsResponse(
            channel_id=s.channel_id,
            enabled=s.enabled,
            min_role_chat=s.min_role_chat,
            max_duration_seconds=s.max_duration_seconds,
            max_queue_size=s.max_queue_size,
        )
    except Exception as e:
        logger.exception(f"Failed to get video queue settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch settings") from None


@router.put("/settings", response_model=VideoQueueSettingsResponse)
async def update_settings(
    body: VideoQueueSettingsUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueSettingsResponse:
    """Update video queue settings."""
    if all(
        v is None
        for v in [body.enabled, body.min_role_chat, body.max_duration_seconds, body.max_queue_size]
    ):
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        settings_repo = VideoQueueSettingsRepository(pool)
        s = await settings_repo.update_settings(
            channel_id,
            enabled=body.enabled,
            min_role_chat=body.min_role_chat,
            max_duration_seconds=body.max_duration_seconds,
            max_queue_size=body.max_queue_size,
        )
        logger.info(f"Channel {channel_id} updated video queue settings")
        return VideoQueueSettingsResponse(
            channel_id=s.channel_id,
            enabled=s.enabled,
            min_role_chat=s.min_role_chat,
            max_duration_seconds=s.max_duration_seconds,
            max_queue_size=s.max_queue_size,
        )
    except Exception as e:
        logger.exception(f"Failed to update video queue settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings") from None


@router.get("/state", response_model=PublicVideoQueueState)
async def get_state(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Dashboard: full queue state for authenticated user's channel."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception as e:
        logger.exception(f"Failed to get video queue state: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None
