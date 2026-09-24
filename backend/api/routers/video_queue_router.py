"""Video queue API routes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from asyncpg import Pool
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import (
    VIDEO_QUEUE_NOTIFY_CHANNEL,
    get_current_channel_id,
    get_db_pool,
    get_notify_hub,
    get_twitch_api,
    require_activated,
)
from core.error_handlers import log_request_failure
from core.rate_limit import RateLimiter
from services import TwitchAPIClient
from services.notify_stream import NotifyWakeHub, StreamCapacityError, encode_sse
from shared.cache import AsyncTTLCache
from shared.errors import (
    AccessDeniedError,
    AppError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)
from shared.instafix_client import fetch_instagram_reel_source
from shared.models.video_queue import (
    VideoQueueBlocklistEntry,
    VideoQueueEntry,
    VideoQueueSettings,
)
from shared.repositories.channel import ChannelRepository
from shared.repositories.video_queue import (
    BLOCKLIST_KINDS,
    VideoQueueBlocklistRepository,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
)
from shared.services.video_queue_admission import (
    AdmissionReason,
    AdmissionRejected,
    VideoQueueAdmissionService,
)
from shared.video_sources import (
    VideoType,
    fetch_twitch_clip_source,
    fetch_video_metadata,
    resolve_video_url,
    unplayable_message,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-queue", tags=["video-queue"])
# Keyed on client_host alone, never client_host:username — _resolve_channel_id
# hits the Twitch API on a cache miss, so keying by (attacker-chosen) username
# would hand out a fresh rate-limit bucket per guessed name for free.
_advance_limiter = RateLimiter(max_calls=30, period=60.0)
_metadata_limiter = RateLimiter(max_calls=30, period=60.0)
_playback_limiter = RateLimiter(max_calls=60, period=60.0)
_stream_limiter = RateLimiter(max_calls=30, period=60.0)
_clip_source_limiter = RateLimiter(max_calls=30, period=60.0)
_reel_source_limiter = RateLimiter(max_calls=30, period=60.0)
_STREAM_HEARTBEAT_SECONDS = 15.0
_STREAM_LEASE_SECONDS = 5 * 60.0


class VideoQueueDisabledError(AccessDeniedError):
    code = "VIDEO_QUEUE.DISABLED"
    user_message = "點播功能目前沒有開啟"


class VideoAlreadyQueuedError(ConflictError):
    code = "VIDEO_QUEUE.ALREADY_EXISTS"
    user_message = "這部影片已經在佇列裡了"


class InvalidVideoUrlError(InvalidInputError):
    code = "VIDEO_QUEUE.INVALID_URL"
    http_status = 422
    user_message = "看不懂這個連結，支援 YouTube、Twitch 剪輯或 Bilibili"


class VideoNotPlayableError(InvalidInputError):
    code = "VIDEO_QUEUE.NOT_PLAYABLE"
    http_status = 422
    user_message = "這部影片無法播放"


class VideoTooLongError(InvalidInputError):
    code = "VIDEO_QUEUE.TOO_LONG"
    http_status = 422
    user_message = "影片長度超過上限"


class VideoMetadataUnverifiableError(InvalidInputError):
    code = "VIDEO_QUEUE.METADATA_UNVERIFIABLE"
    http_status = 422
    user_message = "無法驗證影片資訊，請稍後再試"


class VideoBlockedError(InvalidInputError):
    code = "VIDEO_QUEUE.BLOCKED"
    http_status = 422
    user_message = "這部影片在封鎖清單中"


class VideoQueueOverlayNotFoundError(NotFoundError):
    code = "VIDEO_QUEUE.OVERLAY_NOT_FOUND"
    user_message = "找不到這個顯示來源"


class VideoEntryResponse(BaseModel):
    id: int
    video_id: str
    title: str | None
    duration_seconds: int | None  # for twitch_vod: the capped play window
    is_vertical: bool
    thumbnail_url: str | None  # poster image; None → dashboard shows a placeholder
    start_seconds: int  # twitch_vod seek offset; 0 otherwise
    requested_by: str
    source: str
    video_type: str  # 'youtube' | 'twitch_clip' | 'twitch_vod' | 'bilibili' | 'instagram_reel'
    started_at: datetime | None  # for overlay seek-to-elapsed sync


class PublicVideoQueueState(BaseModel):
    enabled: bool
    volume_percent: int
    current: VideoEntryResponse | None
    queue: list[VideoEntryResponse]
    queue_size: int
    total_queued_duration: int | None  # sum of queued entries' duration_seconds (if all known)


class VideoQueueStreamState(BaseModel):
    """Stream-only payload — deliberately narrower than PublicVideoQueueState.

    No `enabled`: VideoQueueOverlay never reads it, video_queue_settings has no
    NOTIFY trigger, and VideoQueueSettingsRepository caches settings for 15s
    in-process — sending a field that can neither update in real time nor even
    be fresh at connect time would be dishonest. REST callers keep the full
    PublicVideoQueueState unchanged.
    """

    current: VideoEntryResponse | None
    queue: list[VideoEntryResponse]
    queue_size: int
    total_queued_duration: int | None


class VideoQueueSettingsResponse(BaseModel):
    channel_id: str
    overlay_key: UUID
    enabled: bool
    redemption_enabled: bool
    max_duration_redemption: int  # redemption source limit
    max_queue_size: int
    min_view_count: int
    user_cooldown_seconds: int
    max_per_user: int
    max_duration_seconds: int  # global length cap for every source; 0 = no limit
    replay_cooldown_hours: int  # 0 = no limit
    volume_percent: int


class VideoQueueSettingsUpdate(BaseModel):
    enabled: bool | None = None
    redemption_enabled: bool | None = None
    max_duration_redemption: int | None = Field(default=None, ge=30, le=10800)
    max_queue_size: int | None = Field(default=None, ge=1, le=100)
    min_view_count: int | None = Field(default=None, ge=0)
    user_cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    max_per_user: int | None = Field(default=None, ge=0, le=20)
    max_duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    replay_cooldown_hours: int | None = Field(default=None, ge=0, le=168)
    volume_percent: int | None = Field(default=None, ge=0, le=100)


class AddVideoRequest(BaseModel):
    url: str = Field(max_length=2048)


class AdvanceRequest(BaseModel):
    done_id: int | None = None  # None = kickstart (no video finished, just start first queued)
    reason: Literal["completed", "provider_error", "autoplay_blocked", "startup_timeout"] = (
        "completed"
    )


class MetadataUpdate(BaseModel):
    duration_seconds: int = Field(..., ge=1)


class PlaybackStartedRequest(BaseModel):
    signal: Literal["confirmed", "best_effort"]


class VideoHistoryEntry(BaseModel):
    id: int
    video_id: str
    title: str | None
    duration_seconds: int | None
    start_seconds: int
    requested_by: str
    requested_by_id: str | None
    source: str
    video_type: str
    status: str  # 'done' | 'skipped'
    started_at: datetime | None
    ended_at: datetime | None
    creator_id: str | None
    creator_name: str | None


class VideoQueueHistoryResponse(BaseModel):
    entries: list[VideoHistoryEntry]
    #: ISO ``ended_at`` of the last row when a full page was returned — pass it
    #: back as ``?cursor=`` for the next page; ``None`` means no more rows.
    next_cursor: str | None


class VideoQueueRankingResponse(BaseModel):
    rank: int
    video_type: str
    video_id: str
    start_seconds: int
    title: str | None
    thumbnail_url: str | None
    creator_id: str | None
    creator_name: str | None
    play_count: int
    channel_count: int
    last_played_at: datetime
    active_status: str | None
    blocked_kind: str | None


class BlocklistEntryResponse(BaseModel):
    id: int
    kind: str  # 'video' | 'creator' | 'keyword' | 'user'
    video_type: str | None
    value: str
    label: str | None
    created_at: datetime | None


class BlocklistAddRequest(BaseModel):
    kind: str
    video_type: VideoType | None = None
    value: str = Field(min_length=1, max_length=256)
    label: str | None = Field(default=None, max_length=256)


_BLOCK_REASON_LABEL = {
    "video": "這部影片",
    "creator": "這個創作者",
    "keyword": "標題關鍵字",
    "user": "這位使用者",
}


def _blocked_message(entry: VideoQueueBlocklistEntry) -> str:
    return f"{_BLOCK_REASON_LABEL.get(entry.kind, '這部影片')}在封鎖清單中"


def _raise_dashboard_admission_error(error: AdmissionRejected) -> None:
    if error.reason is AdmissionReason.DISABLED:
        raise VideoQueueDisabledError() from error
    if error.reason is AdmissionReason.INVALID_URL:
        raise InvalidVideoUrlError() from error
    if error.reason is AdmissionReason.DUPLICATE:
        raise VideoAlreadyQueuedError() from error
    if error.reason is AdmissionReason.NOT_PLAYABLE:
        reason = str(error.details.get("unplayable_reason") or "")
        raise VideoNotPlayableError(user_message=unplayable_message(reason)) from error
    if error.reason is AdmissionReason.METADATA_UNVERIFIABLE:
        raise VideoMetadataUnverifiableError() from error
    if error.reason is AdmissionReason.TOO_LONG:
        limit = int(error.details.get("limit_seconds") or 0)
        raise VideoTooLongError(user_message=f"影片長度超過上限（{limit // 60} 分鐘）") from error
    if error.reason is AdmissionReason.BLOCKED and error.blocked is not None:
        raise VideoBlockedError(user_message=_blocked_message(error.blocked)) from error
    raise InvalidInputError(user_message="這部影片目前無法加入，請稍後再試") from error


def _protect_capability_response(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


async def _require_overlay_capability(
    request: Request,
    channel_id: str,
    raw_key: str | None,
    settings_repo: VideoQueueSettingsRepository,
    limiter: RateLimiter,
) -> None:
    client_host = request.client.host if request.client else "unknown"
    limiter.require(client_host)
    try:
        overlay_key = UUID(raw_key) if raw_key is not None else None
    except ValueError:
        overlay_key = None
    if overlay_key is None or not await settings_repo.overlay_key_matches(channel_id, overlay_key):
        raise VideoQueueOverlayNotFoundError()


def _blocklist_response(e: VideoQueueBlocklistEntry) -> BlocklistEntryResponse:
    return BlocklistEntryResponse(
        id=e.id,
        kind=e.kind,
        video_type=e.video_type,
        value=e.value,
        label=e.label,
        created_at=e.created_at,
    )


_channel_id_cache: AsyncTTLCache = AsyncTTLCache(
    maxsize=256, ttl=300.0, name="video_queue_router.channel_id"
)


async def _resolve_channel_id(username: str, twitch_api: TwitchAPIClient) -> str:
    if username in _channel_id_cache:
        return _channel_id_cache.get(username)
    user_info = await twitch_api.get_user_by_login(username)
    if not user_info:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel_id = user_info["id"]
    _channel_id_cache.set(username, channel_id)
    return channel_id


def _entry_response(entry: VideoQueueEntry, *, started_at: datetime | None) -> VideoEntryResponse:
    return VideoEntryResponse(
        id=entry.id,
        video_id=entry.video_id,
        title=entry.title,
        duration_seconds=entry.duration_seconds,
        is_vertical=entry.is_vertical,
        thumbnail_url=entry.thumbnail_url,
        start_seconds=entry.start_seconds,
        requested_by=entry.requested_by,
        source=entry.source,
        video_type=entry.video_type,
        started_at=started_at,
    )


def _total_queued_duration(queued: list[VideoQueueEntry]) -> int | None:
    durations = [e.duration_seconds for e in queued]
    if durations and all(d is not None for d in durations):
        return sum(durations)  # type: ignore[arg-type]
    return None


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

    return PublicVideoQueueState(
        enabled=settings.enabled,
        volume_percent=settings.volume_percent,
        current=_entry_response(current, started_at=current.started_at) if current else None,
        queue=[_entry_response(e, started_at=None) for e in queued],
        queue_size=len(queued),
        total_queued_duration=_total_queued_duration(queued),
    )


async def _build_stream_state(
    channel_id: str,
    repo: VideoQueueRepository,
) -> VideoQueueStreamState:
    """Single-connection read for the stream wake path — see
    VideoQueueRepository.get_current_and_queued for why this avoids
    asyncio.gather-ing separate pool.acquire()s like _build_public_state does.
    """
    current, queued = await repo.get_current_and_queued(channel_id)

    return VideoQueueStreamState(
        current=_entry_response(current, started_at=current.started_at) if current else None,
        queue=[_entry_response(e, started_at=None) for e in queued],
        queue_size=len(queued),
        total_queued_duration=_total_queued_duration(queued),
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


@router.get("/public/{username}/stream")
async def stream_public_video_queue(
    request: Request,
    username: str,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    hub: NotifyWakeHub = Depends(get_notify_hub),
) -> StreamingResponse:
    """Stream the current video queue snapshot over one long-lived request.

    Unlike Live Display's append-only event log, there is no cursor/replay
    here: video queue state is a single current snapshot, so a reconnect just
    gets the latest one.
    """
    client_host = request.client.host if request.client else "unknown"
    _stream_limiter.require(client_host)

    channel_id = await _resolve_channel_id(username, twitch_api)
    repo = VideoQueueRepository(pool)
    try:
        subscription = hub.subscribe(VIDEO_QUEUE_NOTIFY_CHANNEL, channel_id)
    except StreamCapacityError:
        raise HTTPException(status_code=429, detail="Too many Video Queue streams") from None
    try:
        state = await _build_stream_state(channel_id, repo)
    except BaseException:
        subscription.close()
        raise

    async def frames() -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        lease_deadline = loop.time() + _STREAM_LEASE_SECONDS
        last_payload = state.model_dump(mode="json")
        try:
            yield encode_sse("snapshot", last_payload)
            while True:
                remaining_lease = lease_deadline - loop.time()
                if remaining_lease <= 0:
                    return
                lease_expiry_wait = remaining_lease <= _STREAM_HEARTBEAT_SECONDS
                try:
                    await asyncio.wait_for(
                        subscription.wait(),
                        timeout=min(_STREAM_HEARTBEAT_SECONDS, remaining_lease),
                    )
                except TimeoutError:
                    if lease_expiry_wait:
                        return
                    yield encode_sse("heartbeat", {"at": datetime.now(UTC).isoformat()})
                    continue

                try:
                    current_state = await _build_stream_state(channel_id, repo)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_request_failure(
                        request,
                        code="STREAM.ITERATION_FAILED",
                        status=500,
                        exc=exc,
                        context={"channel_id": channel_id, "event_class": "occasional"},
                    )
                    # Lets the client tell "we failed mid-stream" apart from the
                    # routine lease-expiry reconnect below — both otherwise look
                    # identical (a clean end of the response body).
                    yield encode_sse("stream_error", {"code": "STREAM.ITERATION_FAILED"})
                    return
                payload = current_state.model_dump(mode="json")
                if payload == last_payload:
                    continue
                last_payload = payload
                yield encode_sse("update", payload)
        finally:
            subscription.close()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "Referrer-Policy": "no-referrer",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/public/{username}/advance", response_model=PublicVideoQueueState)
async def advance_queue(
    request: Request,
    username: str,
    body: AdvanceRequest,
    overlay_key: str | None = Header(default=None, alias="X-Overlay-Key"),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicVideoQueueState:
    """Capability-authorised queue advance for the OBS overlay."""
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        await _require_overlay_capability(
            request, channel_id, overlay_key, settings_repo, _advance_limiter
        )

        if body.done_id is not None:
            # Single transaction: mark done + promote next — eliminates mark_done/set_playing race.
            await repo.advance_queue(channel_id, body.done_id, end_reason=body.reason)
        else:
            await repo.kickstart_if_idle(channel_id)

        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except AppError:
        raise
    except Exception:
        LOGGER.exception("Failed to advance video queue")
        raise HTTPException(status_code=500, detail="Failed to advance queue") from None


@router.patch("/public/{username}/entries/{entry_id}/metadata", status_code=204)
async def update_entry_metadata(
    request: Request,
    username: str,
    entry_id: int,
    body: MetadataUpdate,
    overlay_key: str | None = Header(default=None, alias="X-Overlay-Key"),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> None:
    """Capability-authorised metadata fallback, scoped to entry + channel."""
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        await _require_overlay_capability(
            request, channel_id, overlay_key, settings_repo, _metadata_limiter
        )
        await repo.update_duration(entry_id, body.duration_seconds, channel_id)
    except HTTPException:
        raise
    except AppError:
        raise
    except Exception:
        LOGGER.exception("Failed to update video queue metadata")
        raise HTTPException(status_code=500, detail="Failed to update metadata") from None


@router.post(
    "/public/{username}/entries/{entry_id}/playback-started",
    status_code=204,
)
async def report_playback_started(
    request: Request,
    username: str,
    entry_id: int,
    body: PlaybackStartedRequest,
    overlay_key: str | None = Header(default=None, alias="X-Overlay-Key"),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> None:
    """Record the overlay's idempotent, capability-authorised start signal."""
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        await _require_overlay_capability(
            request, channel_id, overlay_key, settings_repo, _playback_limiter
        )
        await repo.mark_playback_started(entry_id, channel_id, body.signal)
    except HTTPException:
        raise
    except AppError:
        raise
    except Exception:
        LOGGER.exception("Failed to record video queue playback start")
        raise HTTPException(status_code=500, detail="Failed to record playback start") from None


class ClipSourceResponse(BaseModel):
    url: str


@router.get("/public/{username}/entries/{entry_id}/clip-source", response_model=ClipSourceResponse)
async def get_clip_source(
    request: Request,
    username: str,
    entry_id: int,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> ClipSourceResponse:
    """Unauthenticated — resolve a queued Twitch clip to a signed, directly
    playable MP4 URL so the OBS overlay can autoplay it in a `<video>` (the
    embed iframe cannot autoplay in OBS). Scoped to an entry that is actually
    in this channel's queue; 404s so the overlay falls back to the iframe.

    See shared.video_sources.fetch_twitch_clip_source — this is an unofficial,
    best-effort Twitch dependency.
    """
    client_host = request.client.host if request.client else "unknown"
    _clip_source_limiter.require(client_host)
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        entry = await VideoQueueRepository(pool).get_entry_for_channel(entry_id, channel_id)
        if entry is None or entry.video_type != "twitch_clip":
            raise HTTPException(status_code=404, detail="Clip entry not found")
        url = await fetch_twitch_clip_source(entry.video_id)
        if not url:
            raise HTTPException(status_code=404, detail="Clip source unavailable")
        return ClipSourceResponse(url=url)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to resolve twitch clip source")
        raise HTTPException(status_code=500, detail="Failed to resolve clip source") from None


class ReelSourceResponse(BaseModel):
    url: str


@router.get("/public/{username}/entries/{entry_id}/reel-source", response_model=ReelSourceResponse)
async def get_reel_source(
    request: Request,
    username: str,
    entry_id: int,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    app_settings: Settings = Depends(get_settings),
) -> ReelSourceResponse:
    """Unauthenticated — resolve a queued Instagram Reel to a directly playable
    CDN MP4 URL for the OBS overlay's `<video>` (Instagram has no embeddable
    fallback surface, unlike Twitch's clips.twitch.tv/embed). Scoped to an
    entry that is actually in this channel's queue; 404s on any failure so
    the overlay skips to the next entry instead of stalling.

    See shared.instafix_client.fetch_instagram_reel_source — this is an
    unofficial, best-effort dependency on the self-hosted InstaFix proxy.
    """
    client_host = request.client.host if request.client else "unknown"
    _reel_source_limiter.require(client_host)
    try:
        channel_id = await _resolve_channel_id(username, twitch_api)
        entry = await VideoQueueRepository(pool).get_entry_for_channel(entry_id, channel_id)
        if entry is None or entry.video_type != "instagram_reel":
            raise HTTPException(status_code=404, detail="Reel entry not found")
        url = await fetch_instagram_reel_source(entry.video_id, app_settings.instafix_host)
        if not url:
            raise HTTPException(status_code=404, detail="Reel source unavailable")
        return ReelSourceResponse(url=url)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to resolve instagram reel source")
        raise HTTPException(status_code=500, detail="Failed to resolve reel source") from None


@router.delete("/skip", status_code=200, response_model=PublicVideoQueueState)
async def skip_current(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Skip the currently playing video."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        await repo.skip_current_atomic(channel_id)
        LOGGER.info("Channel %s skipped video queue entry", channel_id)
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        LOGGER.exception("Failed to skip video")
        raise HTTPException(status_code=500, detail="Failed to skip video") from None


@router.delete("/clear", status_code=200, response_model=PublicVideoQueueState)
async def clear_queue(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Clear the entire queue (current + all queued)."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        await repo.clear_all_atomic(channel_id)
        LOGGER.info("Channel %s cleared video queue", channel_id)
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        LOGGER.exception("Failed to clear video queue")
        raise HTTPException(status_code=500, detail="Failed to clear queue") from None


def _settings_response(s: VideoQueueSettings) -> VideoQueueSettingsResponse:
    return VideoQueueSettingsResponse(
        channel_id=s.channel_id,
        overlay_key=s.overlay_key,
        enabled=s.enabled,
        redemption_enabled=s.redemption_enabled,
        max_duration_redemption=s.max_duration_redemption,
        max_queue_size=s.max_queue_size,
        min_view_count=s.min_view_count,
        user_cooldown_seconds=s.user_cooldown_seconds,
        max_per_user=s.max_per_user,
        max_duration_seconds=s.max_duration_seconds,
        replay_cooldown_hours=s.replay_cooldown_hours,
        volume_percent=s.volume_percent,
    )


@router.get("/settings", response_model=VideoQueueSettingsResponse)
async def get_video_queue_settings(
    response: Response,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueSettingsResponse:
    """Get video queue settings."""
    _protect_capability_response(response)
    try:
        settings_repo = VideoQueueSettingsRepository(pool)
        return _settings_response(await settings_repo.get_or_create(channel_id))
    except Exception:
        LOGGER.exception("Failed to get video queue settings")
        raise HTTPException(status_code=500, detail="Failed to fetch settings") from None


@router.put("/settings", response_model=VideoQueueSettingsResponse)
async def update_video_queue_settings(
    body: VideoQueueSettingsUpdate,
    response: Response,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueSettingsResponse:
    """Update video queue settings."""
    _protect_capability_response(response)
    if all(v is None for v in body.model_dump().values()):
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
            max_duration_seconds=body.max_duration_seconds,
            replay_cooldown_hours=body.replay_cooldown_hours,
            volume_percent=body.volume_percent,
        )
        LOGGER.info("Channel %s updated video queue settings", channel_id)
        return _settings_response(s)
    except Exception:
        LOGGER.exception("Failed to update video queue settings")
        raise HTTPException(status_code=500, detail="Failed to update settings") from None


@router.post("/settings/rotate-key", response_model=VideoQueueSettingsResponse)
async def rotate_video_queue_overlay_key(
    response: Response,
    _action: Literal["video-queue"] = Header(alias="X-Niibot-Action"),
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueSettingsResponse:
    """Rotate the OBS overlay capability and invalidate previous URLs."""
    _protect_capability_response(response)
    try:
        settings_repo = VideoQueueSettingsRepository(pool)
        settings = await settings_repo.rotate_overlay_key(channel_id)
        LOGGER.info("Channel %s rotated video queue overlay key", channel_id)
        return _settings_response(settings)
    except Exception:
        LOGGER.exception("Failed to rotate video queue overlay key")
        raise HTTPException(status_code=500, detail="Failed to rotate overlay key") from None


@router.post("/advance", response_model=PublicVideoQueueState)
async def advance_queue_from_dashboard(
    body: AdvanceRequest,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Authenticated dashboard kickstart/advance path."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        if body.done_id is not None:
            await repo.advance_queue(channel_id, body.done_id, end_reason=body.reason)
        else:
            await repo.kickstart_if_idle(channel_id)
        return await _build_public_state(channel_id, repo, settings_repo)
    except Exception:
        LOGGER.exception("Failed to advance video queue from dashboard")
        raise HTTPException(status_code=500, detail="Failed to advance queue") from None


@router.get("/state", response_model=PublicVideoQueueState)
async def get_state(
    _: None = Depends(require_activated),
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


@router.get("/history", response_model=VideoQueueHistoryResponse)
async def get_history(
    limit: int = 50,
    cursor: str | None = None,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> VideoQueueHistoryResponse:
    """Dashboard: recently played / skipped entries, newest first, keyset-paged."""
    limit = max(1, min(limit, 100))
    before: datetime | None = None
    if cursor:
        try:
            before = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    try:
        entries = await VideoQueueRepository(pool).get_history(
            channel_id, limit=limit, before=before
        )
        next_cursor = (
            entries[-1].ended_at.isoformat()
            if len(entries) == limit and entries[-1].ended_at
            else None
        )
        return VideoQueueHistoryResponse(
            entries=[
                VideoHistoryEntry(
                    id=e.id,
                    video_id=e.video_id,
                    title=e.title,
                    duration_seconds=e.duration_seconds,
                    start_seconds=e.start_seconds,
                    requested_by=e.requested_by,
                    requested_by_id=e.requested_by_id,
                    source=e.source,
                    video_type=e.video_type,
                    status=e.status,
                    started_at=e.started_at,
                    ended_at=e.ended_at,
                    creator_id=e.creator_id,
                    creator_name=e.creator_name,
                )
                for e in entries
            ],
            next_cursor=next_cursor,
        )
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to get video queue history")
        raise HTTPException(status_code=500, detail="Failed to fetch history") from None


@router.get("/rankings", response_model=list[VideoQueueRankingResponse])
async def get_rankings(
    response: Response,
    scope: Literal["channel", "global"] = "channel",
    days: int = Query(default=7),
    video_type: VideoType | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[VideoQueueRankingResponse]:
    """Private workbench rankings; global results contain aggregates only."""
    if days not in {7, 30}:
        raise HTTPException(status_code=422, detail="days must be 7 or 30")
    _protect_capability_response(response)
    try:
        entries = await VideoQueueRepository(pool).get_rankings(
            channel_id,
            scope=scope,
            days=days,
            video_type=video_type,
            limit=limit,
        )
        return [
            VideoQueueRankingResponse(
                rank=e.rank,
                video_type=e.video_type,
                video_id=e.video_id,
                start_seconds=e.start_seconds,
                title=e.title,
                thumbnail_url=e.thumbnail_url,
                creator_id=e.creator_id,
                creator_name=e.creator_name,
                play_count=e.play_count,
                channel_count=e.channel_count,
                last_played_at=e.last_played_at,
                active_status=e.active_status,
                blocked_kind=e.blocked_kind,
            )
            for e in entries
        ]
    except Exception:
        LOGGER.exception("Failed to get video queue rankings")
        raise HTTPException(status_code=500, detail="Failed to fetch rankings") from None


async def video_queue_history_retention_loop(db_manager) -> None:  # type: ignore[no-untyped-def]
    """Delete video_queue history rows past the retention window, once a day."""
    while True:
        try:
            await asyncio.sleep(86_400)
            if not db_manager.is_connected:
                continue
            removed = await VideoQueueRepository(db_manager.pool).prune_history()
            if removed:
                LOGGER.info("video_queue_history_pruned", extra={"rows": removed})
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("video_queue_history_prune_failed")


@router.get("/blocklist", response_model=list[BlocklistEntryResponse])
async def list_blocklist(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[BlocklistEntryResponse]:
    """Dashboard: this channel's Video Queue blocklist rules, newest first."""
    try:
        entries = await VideoQueueBlocklistRepository(pool).list_entries(channel_id)
        return [_blocklist_response(e) for e in entries]
    except Exception:
        LOGGER.exception("Failed to list video queue blocklist")
        raise HTTPException(status_code=500, detail="Failed to fetch blocklist") from None


@router.post("/blocklist", response_model=BlocklistEntryResponse, status_code=201)
async def add_blocklist_entry(
    body: BlocklistAddRequest,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> BlocklistEntryResponse:
    """Dashboard: add a blocklist rule. Idempotent per (kind, value)."""
    if body.kind not in BLOCKLIST_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {BLOCKLIST_KINDS}")
    if body.video_type is not None and body.kind not in {"video", "creator"}:
        raise HTTPException(
            status_code=422,
            detail="video_type is only valid for video and creator rules",
        )
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="value must not be blank")
    video_type = body.video_type
    if body.kind == "video" and "/" in value:
        # A URL, not a bare native id (every native id — YouTube id, BV id,
        # clip slug, IG shortcode — is a single path segment with no slash).
        # Normalize it server-side through the same cascade admission uses
        # (resolves b23.tv/share redirects, av→BV, etc.) instead of trusting
        # a client-side regex, and never persist or log the raw URL — it may
        # carry tracking params (utm_*, si, igsh, ...).
        resolved = await resolve_video_url(value)
        if resolved is None:
            raise HTTPException(status_code=422, detail="無法辨識的影片網址")
        value = resolved.video_id
        video_type = resolved.video_type
    try:
        entry = await VideoQueueBlocklistRepository(pool).add(
            channel_id,
            body.kind,
            value,
            video_type=video_type,
            label=(body.label.strip() or None) if body.label else None,
            created_by=channel_id,
        )
        LOGGER.info("Channel %s blocked %s %r", channel_id, body.kind, value)
        return _blocklist_response(entry)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to add video queue blocklist entry")
        raise HTTPException(status_code=500, detail="Failed to add blocklist entry") from None


@router.delete("/blocklist/{entry_id}", status_code=204)
async def delete_blocklist_entry(
    entry_id: int,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> None:
    """Dashboard: remove a blocklist rule."""
    try:
        removed = await VideoQueueBlocklistRepository(pool).remove(channel_id, entry_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Blocklist entry not found")
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to delete video queue blocklist entry")
        raise HTTPException(status_code=500, detail="Failed to delete blocklist entry") from None


@router.post("/entries/{entry_id}/set-next", response_model=PublicVideoQueueState)
async def set_entry_as_next(
    entry_id: int,
    _: None = Depends(require_activated),
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
        LOGGER.info("Channel %s set entry %s as next", channel_id, entry_id)
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to set entry as next")
        raise HTTPException(status_code=500, detail="Failed to reorder queue") from None


@router.post("/entries/{entry_id}/play-now", response_model=PublicVideoQueueState)
async def play_entry_now(
    entry_id: int,
    _: None = Depends(require_activated),
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
        LOGGER.info("Channel %s played entry %s immediately", channel_id, entry_id)
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to play entry immediately")
        raise HTTPException(status_code=500, detail="Failed to play entry") from None


@router.delete("/entries/{entry_id}", response_model=PublicVideoQueueState)
async def remove_queue_entry(
    entry_id: int,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> PublicVideoQueueState:
    """Remove a specific queued entry from the queue."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        removed = await repo.mark_skipped(entry_id, channel_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Entry not found or not in removable state")
        LOGGER.info("Channel %s removed entry %s from queue", channel_id, entry_id)
        return await _build_public_state(channel_id, repo, settings_repo)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to remove queue entry")
        raise HTTPException(status_code=500, detail="Failed to remove entry") from None


@router.post("/entries", response_model=PublicVideoQueueState, status_code=201)
async def add_video_entry(
    body: AddVideoRequest,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
    app_settings: Settings = Depends(get_settings),
) -> PublicVideoQueueState:
    """Broadcaster directly adds a video to the queue from the dashboard."""
    try:
        repo = VideoQueueRepository(pool)
        settings_repo = VideoQueueSettingsRepository(pool)
        channel_repo = ChannelRepository(pool)

        async def resolve_requester() -> str:
            return await channel_repo.get_broadcaster_display_name(channel_id) or channel_id

        admission = VideoQueueAdmissionService(
            repo,
            settings_repo,
            VideoQueueBlocklistRepository(pool),
        )
        try:
            result = await admission.admit(
                channel_id=channel_id,
                url=body.url,
                requested_by=resolve_requester,
                source="dashboard",
                resolve=lambda url: resolve_video_url(url),
                fetch_metadata=lambda resolved: fetch_video_metadata(
                    resolved,
                    youtube_api_key=app_settings.youtube_api_key,
                    twitch_client_id=app_settings.client_id,
                    twitch_client_secret=app_settings.client_secret,
                    instafix_host=app_settings.instafix_host,
                ),
            )
        except AdmissionRejected as error:
            _raise_dashboard_admission_error(error)

        LOGGER.info(
            "Channel %s added %s %s from dashboard",
            channel_id,
            result.resolved.video_type,
            result.resolved.video_id,
        )
        return await _build_public_state(channel_id, repo, settings_repo)
    except (HTTPException, AppError):
        raise
    except Exception:
        LOGGER.exception("Failed to add video entry")
        raise HTTPException(status_code=500, detail="Failed to add video") from None
