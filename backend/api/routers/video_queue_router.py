"""Video queue API routes."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import TwitchAPIClient
from shared.repositories.channel import ChannelRepository
from shared.repositories.video_queue import (
    SOURCE_PRIORITY,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    extract_twitch_clip_slug,
    extract_youtube_info,
    fetch_twitch_clip_info,
    fetch_yt_info,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-queue", tags=["video-queue"])


class VideoEntryResponse(BaseModel):
    id: int
    video_id: str
    title: str | None
    duration_seconds: int | None
    is_vertical: bool
    requested_by: str
    source: str
    video_type: str  # 'youtube' | 'twitch_clip'
    started_at: datetime | None  # for overlay seek-to-elapsed sync


class PublicVideoQueueState(BaseModel):
    enabled: bool
    current: VideoEntryResponse | None
    queue: list[VideoEntryResponse]
    queue_size: int
    total_queued_duration: int | None  # sum of queued entries' duration_seconds (if all known)


class VideoQueueSettingsResponse(BaseModel):
    channel_id: str
    enabled: bool
    redemption_enabled: bool
    max_duration_redemption: int  # redemption source limit
    max_queue_size: int
    min_view_count: int
    user_cooldown_seconds: int
    max_per_user: int


class VideoQueueSettingsUpdate(BaseModel):
    enabled: bool | None = None
    redemption_enabled: bool | None = None
    max_duration_redemption: int | None = Field(default=None, ge=30, le=10800)
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


_CHANNEL_ID_CACHE: dict[str, tuple[str, float]] = {}
_CHANNEL_ID_TTL = 300.0  # 5 minutes


async def _resolve_channel_id(username: str, twitch_api: TwitchAPIClient) -> str:
    cached = _CHANNEL_ID_CACHE.get(username)
    if cached and time.monotonic() - cached[1] < _CHANNEL_ID_TTL:
        return cached[0]
    user_info = await twitch_api.get_user_by_login(username)
    if not user_info:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel_id = user_info["id"]
    _CHANNEL_ID_CACHE[username] = (channel_id, time.monotonic())
    return channel_id


async def _build_public_state(
    channel_id: str,
    repo: VideoQueueRepository,
    settings_repo: VideoQueueSettingsRepository,
) -> PublicVideoQueueState:
    settings, current, queued = await asyncio.gather(
        settings_repo.get_or_create(channel_id),
        repo.get_current(channel_id),
        repo.get_queued(channel_id),
    )

    durations = [e.duration_seconds for e in queued]
    total_queued_duration: int | None = None
    if durations and all(d is not None for d in durations):
        total_queued_duration = sum(durations)  # type: ignore[arg-type]

    return PublicVideoQueueState(
        enabled=settings.enabled,
        current=VideoEntryResponse(
            id=current.id,
            video_id=current.video_id,
            title=current.title,
            duration_seconds=current.duration_seconds,
            is_vertical=current.is_vertical,
            requested_by=current.requested_by,
            source=current.source,
            video_type=current.video_type,
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
                source=e.source,
                video_type=e.video_type,
                started_at=None,
            )
            for e in queued
        ],
        queue_size=len(queued),
        total_queued_duration=total_queued_duration,
    )


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
        LOGGER.exception("Failed to get public video queue state")
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
            # Kickstart: atomically promote next queued entry if nothing is playing
            await repo.kickstart_if_idle(channel_id)

        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to advance video queue")
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
        LOGGER.exception("Failed to update video queue metadata")
        raise HTTPException(status_code=500, detail="Failed to update metadata") from None


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
        LOGGER.info(f"Channel {channel_id} skipped video queue entry")
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        LOGGER.exception("Failed to skip video")
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
        LOGGER.info(f"Channel {channel_id} cleared video queue")
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        LOGGER.exception("Failed to clear video queue")
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
            redemption_enabled=s.redemption_enabled,
            max_duration_redemption=s.max_duration_redemption,
            max_queue_size=s.max_queue_size,
            min_view_count=s.min_view_count,
            user_cooldown_seconds=s.user_cooldown_seconds,
            max_per_user=s.max_per_user,
        )
    except Exception:
        LOGGER.exception("Failed to get video queue settings")
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
            body.redemption_enabled,
            body.max_duration_redemption,
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
            redemption_enabled=body.redemption_enabled,
            max_duration_redemption=body.max_duration_redemption,
            max_queue_size=body.max_queue_size,
            min_view_count=body.min_view_count,
            user_cooldown_seconds=body.user_cooldown_seconds,
            max_per_user=body.max_per_user,
        )
        LOGGER.info(f"Channel {channel_id} updated video queue settings")
        return VideoQueueSettingsResponse(
            channel_id=s.channel_id,
            enabled=s.enabled,
            redemption_enabled=s.redemption_enabled,
            max_duration_redemption=s.max_duration_redemption,
            max_queue_size=s.max_queue_size,
            min_view_count=s.min_view_count,
            user_cooldown_seconds=s.user_cooldown_seconds,
            max_per_user=s.max_per_user,
        )
    except Exception:
        LOGGER.exception("Failed to update video queue settings")
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
        LOGGER.exception("Failed to get video queue state")
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
        LOGGER.info(f"Channel {channel_id} set entry {entry_id} as next")
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to set entry as next")
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
        promoted = await repo.play_immediately(entry_id, channel_id)
        if not promoted:
            raise HTTPException(status_code=404, detail="Entry not found or not in queued state")
        LOGGER.info(f"Channel {channel_id} played entry {entry_id} immediately")
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to play entry immediately")
        raise HTTPException(status_code=500, detail="Failed to play entry") from None


@router.post("/entries", response_model=PublicVideoQueueState, status_code=201)
async def add_video_entry(
    body: AddVideoRequest,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
    app_settings: Settings = Depends(get_settings),
) -> PublicVideoQueueState:
    """Broadcaster directly adds a video to the queue from the dashboard."""
    # Detect URL type: try YouTube first, then Twitch clip
    video_id, is_vertical = extract_youtube_info(body.url)
    clip_slug: str | None = None
    if not video_id:
        clip_slug = extract_twitch_clip_slug(body.url)
        if not clip_slug:
            raise HTTPException(status_code=422, detail="Invalid YouTube or Twitch clip URL")

    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)

        # Module-level gate: dashboard adds respect the enabled toggle
        settings = await settings_repo.get_or_create(channel_id)
        if not settings.enabled:
            raise HTTPException(status_code=403, detail="Video queue is disabled")

        # Exactly one of clip_slug or video_id is non-None here (the 422 raise above ensures this).
        active_id: str = clip_slug if clip_slug else video_id  # type: ignore[assignment]
        if await repo.video_is_active(channel_id, active_id):
            raise HTTPException(status_code=409, detail="Video already in queue")

        # Dashboard adds bypass max_queue_size and min_view_count — broadcaster has full authority over their own queue
        if clip_slug:
            title, duration_seconds, _ = await fetch_twitch_clip_info(
                clip_slug, app_settings.client_id, app_settings.client_secret
            )
            video_id = clip_slug
            is_vertical = False
            video_type = "twitch_clip"
        else:
            if video_id is None:
                raise HTTPException(status_code=422, detail="No valid video source")
            title, duration_seconds, _, is_vertical_from_api = await fetch_yt_info(
                video_id, app_settings.youtube_api_key
            )
            is_vertical = is_vertical or is_vertical_from_api
            video_type = "youtube"

        # Look up broadcaster display name for the requested_by field
        channel_repo = ChannelRepository(pool)
        requested_by: str = (
            await channel_repo.get_broadcaster_display_name(channel_id) or channel_id
        )

        await repo.add(
            channel_id=channel_id,
            video_id=video_id,
            requested_by=requested_by,
            source="dashboard",
            title=title,
            duration_seconds=duration_seconds,
            is_vertical=is_vertical,
            video_type=video_type,
            priority=SOURCE_PRIORITY["dashboard"],
        )
        LOGGER.info(f"Channel {channel_id} added {video_type} {video_id} from dashboard")
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to add video entry")
        raise HTTPException(status_code=500, detail="Failed to add video") from None
