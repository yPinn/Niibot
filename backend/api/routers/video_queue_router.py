"""Video queue API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import TwitchAPIClient
from shared.repositories.video_queue import (
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    extract_youtube_info,
    fetch_yt_info,
)

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
    is_vertical: bool
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
    chat_enabled: bool
    redemption_enabled: bool
    min_role_chat: str
    max_duration_seconds: int
    max_queue_size: int
    min_view_count: int
    user_cooldown_seconds: int
    max_per_user: int


class VideoQueueSettingsUpdate(BaseModel):
    enabled: bool | None = None
    chat_enabled: bool | None = None
    redemption_enabled: bool | None = None
    min_role_chat: str | None = Field(
        default=None, pattern="^(everyone|subscriber|vip|moderator|broadcaster)$"
    )
    max_duration_seconds: int | None = Field(default=None, ge=30, le=10800)
    max_queue_size: int | None = Field(default=None, ge=1, le=100)
    min_view_count: int | None = Field(default=None, ge=0)
    user_cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    max_per_user: int | None = Field(default=None, ge=0, le=20)


class AddVideoRequest(BaseModel):
    url: str = Field(max_length=2048)


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
            is_vertical=current.is_vertical,
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
                is_vertical=e.is_vertical,
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
    except Exception:
        logger.exception("Failed to get public video queue state")
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

    NOTE: This endpoint is intentionally unauthenticated. It is called directly by the
    OBS browser source overlay, which has no mechanism to carry session cookies. The
    accepted security trade-off: the only actions available are advancing the queue
    and reading public queue state — no destructive or private operations are exposed.
    """
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)

        if body.done_id:
            # advance_queue atomically marks done_id as done and promotes the next
            # queued entry in a single transaction, eliminating the race condition
            # between mark_done and set_playing.
            await repo.advance_queue(channel_id, body.done_id)
        else:
            # Kickstart: no video finished, just promote if nothing is playing
            current = await repo.get_current(channel_id)
            if current is None:
                queued = await repo.get_queued(channel_id)
                if queued:
                    await repo.set_playing(queued[0].id)

        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to advance video queue")
        raise HTTPException(status_code=500, detail="Failed to advance queue") from None


@router.patch("/public/{username}/entries/{entry_id}/metadata", status_code=204)
async def update_entry_metadata(
    username: str,
    entry_id: int,
    body: MetadataUpdate,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> None:
    """Overlay reports duration after the YouTube player loads (fallback for API misses).

    NOTE: This endpoint is intentionally unauthenticated. It is called by the OBS
    browser source overlay after the YouTube player reports its loaded duration. The
    accepted security trade-off: the only writable field is duration_seconds, scoped
    to a specific entry_id and channel — no sensitive data is accessible or mutable.
    """
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        await repo.update_duration(entry_id, body.duration_seconds, channel_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to update video queue metadata")
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
        await repo.skip_current_atomic(channel_id)
        logger.info(f"Channel {channel_id} skipped video queue entry")
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        logger.exception("Failed to skip video")
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
            await repo.mark_skipped(current.id, channel_id)
        await repo.clear_queued(channel_id)
        logger.info(f"Channel {channel_id} cleared video queue")
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        logger.exception("Failed to clear video queue")
        raise HTTPException(status_code=500, detail="Failed to clear queue") from None


@router.get("/settings", response_model=VideoQueueSettingsResponse)
async def get_video_queue_settings(
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
            chat_enabled=s.chat_enabled,
            redemption_enabled=s.redemption_enabled,
            min_role_chat=s.min_role_chat,
            max_duration_seconds=s.max_duration_seconds,
            max_queue_size=s.max_queue_size,
            min_view_count=s.min_view_count,
            user_cooldown_seconds=s.user_cooldown_seconds,
            max_per_user=s.max_per_user,
        )
    except Exception:
        logger.exception("Failed to get video queue settings")
        raise HTTPException(status_code=500, detail="Failed to fetch settings") from None


@router.put("/settings", response_model=VideoQueueSettingsResponse)
async def update_video_queue_settings(
    body: VideoQueueSettingsUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueSettingsResponse:
    """Update video queue settings."""
    if all(
        v is None
        for v in [
            body.enabled,
            body.chat_enabled,
            body.redemption_enabled,
            body.min_role_chat,
            body.max_duration_seconds,
            body.max_queue_size,
            body.min_view_count,
            body.user_cooldown_seconds,
            body.max_per_user,
        ]
    ):
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        settings_repo = VideoQueueSettingsRepository(pool)
        s = await settings_repo.update_settings(
            channel_id,
            enabled=body.enabled,
            chat_enabled=body.chat_enabled,
            redemption_enabled=body.redemption_enabled,
            min_role_chat=body.min_role_chat,
            max_duration_seconds=body.max_duration_seconds,
            max_queue_size=body.max_queue_size,
            min_view_count=body.min_view_count,
            user_cooldown_seconds=body.user_cooldown_seconds,
            max_per_user=body.max_per_user,
        )
        logger.info(f"Channel {channel_id} updated video queue settings")
        return VideoQueueSettingsResponse(
            channel_id=s.channel_id,
            enabled=s.enabled,
            chat_enabled=s.chat_enabled,
            redemption_enabled=s.redemption_enabled,
            min_role_chat=s.min_role_chat,
            max_duration_seconds=s.max_duration_seconds,
            max_queue_size=s.max_queue_size,
            min_view_count=s.min_view_count,
            user_cooldown_seconds=s.user_cooldown_seconds,
            max_per_user=s.max_per_user,
        )
    except Exception:
        logger.exception("Failed to update video queue settings")
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
    except Exception:
        logger.exception("Failed to get video queue state")
        raise HTTPException(status_code=500, detail="Failed to fetch queue state") from None


@router.post("/entries/{entry_id}/set-next", response_model=PublicVideoQueueState)
async def set_entry_as_next(
    entry_id: int,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Move a queued entry to the front of the queue (play next)."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        moved = await repo.set_as_next(entry_id, channel_id)
        if not moved:
            raise HTTPException(status_code=404, detail="Entry not found or not in queued state")
        logger.info(f"Channel {channel_id} set entry {entry_id} as next")
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to set entry as next")
        raise HTTPException(status_code=500, detail="Failed to reorder queue") from None


@router.post("/entries/{entry_id}/play-now", response_model=PublicVideoQueueState)
async def play_entry_now(
    entry_id: int,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Skip current video and immediately start playing the specified queued entry."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        await repo.play_immediately(entry_id, channel_id)
        logger.info(f"Channel {channel_id} played entry {entry_id} immediately")
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to play entry immediately")
        raise HTTPException(status_code=500, detail="Failed to play entry") from None


@router.post("/entries", response_model=PublicVideoQueueState, status_code=201)
async def add_video_entry(
    body: AddVideoRequest,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Broadcaster directly adds a video to the queue from the dashboard."""
    video_id, is_vertical = extract_youtube_info(body.url)
    if not video_id:
        raise HTTPException(status_code=422, detail="Invalid YouTube URL")

    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)

        # Enforce queue size limit
        settings = await settings_repo.get_or_create(channel_id)
        queue_size = await repo.get_queue_size(channel_id)
        if queue_size >= settings.max_queue_size:
            raise HTTPException(status_code=409, detail="Queue is full")

        if await repo.video_is_active(channel_id, video_id):
            raise HTTPException(status_code=409, detail="Video already in queue")

        # Fetch YouTube metadata (graceful fallback if no API key or request fails)
        api_key = get_settings().youtube_api_key
        # Dashboard adds bypass min_view_count — broadcaster has full authority over their own queue
        title, duration_seconds, _, is_vertical_from_api = await fetch_yt_info(video_id, api_key)
        is_vertical = is_vertical or is_vertical_from_api

        # Look up broadcaster display name for the requested_by field
        row = await pool.fetchrow(
            "SELECT u.display_name, la.username "
            "FROM user_linked_accounts la "
            "JOIN users u ON u.id = la.user_id "
            "WHERE la.platform = 'twitch' AND la.platform_user_id = $1",
            channel_id,
        )
        requested_by: str = (row["display_name"] or row["username"]) if row else channel_id

        await repo.add(
            channel_id=channel_id,
            video_id=video_id,
            requested_by=requested_by,
            source="dashboard",
            title=title,
            duration_seconds=duration_seconds,
            is_vertical=is_vertical,
        )
        logger.info(f"Channel {channel_id} added video {video_id} from dashboard")
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to add video entry")
        raise HTTPException(status_code=500, detail="Failed to add video") from None
