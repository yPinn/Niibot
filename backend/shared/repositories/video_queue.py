"""Repository for video_queue and video_queue_settings tables.

Also contains shared utilities:
  - extract_youtube_id(): pure string parsing, used by bot and channel_points
  - fetch_yt_info(): YouTube Data API v3 call, used by bot and channel_points
"""

from __future__ import annotations

import logging
import re

import aiohttp
import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.video_queue import VideoQueueEntry, VideoQueueSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YouTube utilities
# ---------------------------------------------------------------------------

_YT_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:"
    r"youtube\.com/watch\?(?:.*&)?v=|"
    r"youtu\.be/|"
    r"youtube\.com/shorts/"
    r")([A-Za-z0-9_-]{11})"
)

_ISO8601_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def extract_youtube_id(text: str) -> str | None:
    """Extract 11-char YouTube video ID from a URL string. Returns None if not found."""
    m = _YT_RE.search(text)
    return m.group(1) if m else None


def _parse_iso8601_duration(duration: str) -> int:
    """Parse ISO 8601 duration (e.g. 'PT1H3M45S') to total seconds."""
    m = _ISO8601_RE.match(duration)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


async def fetch_yt_info(
    video_id: str,
    api_key: str,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, int | None]:
    """Fetch video title and duration via YouTube Data API v3.

    If `session` is None a temporary one-shot session is created and closed.
    Returns (title, duration_seconds). Both None on any failure or missing key.
    """
    if not api_key:
        return None, None

    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,contentDetails&id={video_id}&key={api_key}"
    )
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                logger.warning(f"[YouTube API] Unexpected status {resp.status} for {video_id}")
                return None, None
            data = await resp.json()
            items = data.get("items", [])
            if not items:
                return None, None  # video not found / private
            item = items[0]
            title: str | None = item.get("snippet", {}).get("title")
            raw_duration: str = item.get("contentDetails", {}).get("duration", "")
            duration_seconds = _parse_iso8601_duration(raw_duration) if raw_duration else 0
            return title, duration_seconds or None
    except Exception as exc:
        logger.warning(f"[YouTube API] fetch_yt_info failed for {video_id}: {exc}")
        return None, None
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Column constants
# ---------------------------------------------------------------------------

_ENTRY_COLUMNS = (
    "id, channel_id, video_id, title, duration_seconds, requested_by, "
    "source, status, created_at, started_at, ended_at"
)

_SETTINGS_COLUMNS = (
    "channel_id, enabled, min_role_chat, max_duration_seconds, max_queue_size, "
    "created_at, updated_at"
)

_settings_cache = AsyncTTLCache(maxsize=32, ttl=300)


# ---------------------------------------------------------------------------
# VideoQueueRepository
# ---------------------------------------------------------------------------


class VideoQueueRepository:
    """Pure SQL operations for the video_queue table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def add(
        self,
        channel_id: str,
        video_id: str,
        requested_by: str,
        source: str,
        title: str | None = None,
        duration_seconds: int | None = None,
    ) -> VideoQueueEntry:
        """Insert a new entry with status='queued'."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue
                    (channel_id, video_id, title, duration_seconds, requested_by, source)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING {_ENTRY_COLUMNS}
                """,
                channel_id,
                video_id,
                title,
                duration_seconds,
                requested_by,
                source,
            )
            return VideoQueueEntry(**dict(row))

    async def get_current(self, channel_id: str) -> VideoQueueEntry | None:
        """Return the currently playing entry, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                "WHERE channel_id = $1 AND status = 'playing' "
                "ORDER BY started_at ASC LIMIT 1",
                channel_id,
            )
            return VideoQueueEntry(**dict(row)) if row else None

    async def get_queued(self, channel_id: str) -> list[VideoQueueEntry]:
        """Return all queued (not yet playing) entries ordered by created_at ASC."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                "WHERE channel_id = $1 AND status = 'queued' "
                "ORDER BY created_at ASC",
                channel_id,
            )
            return [VideoQueueEntry(**dict(row)) for row in rows]

    async def get_queue_size(self, channel_id: str) -> int:
        """Count entries with status='queued'."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM video_queue WHERE channel_id = $1 AND status = 'queued'",
                channel_id,
            )

    async def video_is_active(self, channel_id: str, video_id: str) -> bool:
        """Return True if video_id is already queued or playing in this channel."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM video_queue "
                "WHERE channel_id = $1 AND video_id = $2 AND status IN ('queued', 'playing')",
                channel_id,
                video_id,
            )
            return count > 0

    async def set_playing(self, entry_id: int) -> None:
        """Transition entry to 'playing'. No-op if not in 'queued' state."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue "
                "SET status = 'playing', started_at = NOW() "
                "WHERE id = $1 AND status = 'queued'",
                entry_id,
            )

    async def update_duration(self, entry_id: int, duration_seconds: int) -> None:
        """Update duration_seconds (overlay fallback report after load)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET duration_seconds = $2 WHERE id = $1",
                entry_id,
                duration_seconds,
            )

    async def mark_done(self, entry_id: int) -> None:
        """Transition entry to 'done'. Only applies when status='playing'."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET status = 'done', ended_at = NOW() "
                "WHERE id = $1 AND status = 'playing'",
                entry_id,
            )

    async def mark_skipped(self, entry_id: int) -> None:
        """Transition entry to 'skipped'. Applies to 'queued' or 'playing'."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                "WHERE id = $1 AND status IN ('queued', 'playing')",
                entry_id,
            )

    async def clear_queued(self, channel_id: str) -> int:
        """Mark all queued entries as skipped. Returns count of affected rows."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                "WHERE channel_id = $1 AND status = 'queued'",
                channel_id,
            )
            return int(result.split()[-1])

    async def find_last_queued_by_user(
        self, channel_id: str, requested_by: str
    ) -> VideoQueueEntry | None:
        """Find the most recently submitted queued entry for a given user (for !vq remove)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                "WHERE channel_id = $1 AND requested_by = $2 AND status = 'queued' "
                "ORDER BY created_at DESC LIMIT 1",
                channel_id,
                requested_by,
            )
            return VideoQueueEntry(**dict(row)) if row else None


# ---------------------------------------------------------------------------
# VideoQueueSettingsRepository
# ---------------------------------------------------------------------------


class VideoQueueSettingsRepository:
    """Pure SQL operations for the video_queue_settings table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_settings_cache,
        key_func=lambda self, channel_id: f"vq_settings:{channel_id}",
    )
    async def get_or_create(self, channel_id: str) -> VideoQueueSettings:
        """Get settings for a channel, creating defaults if not exists."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue_settings (channel_id)
                VALUES ($1)
                ON CONFLICT (channel_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
            )
            return VideoQueueSettings(**dict(row))

    async def update_settings(
        self,
        channel_id: str,
        *,
        enabled: bool | None = None,
        min_role_chat: str | None = None,
        max_duration_seconds: int | None = None,
        max_queue_size: int | None = None,
    ) -> VideoQueueSettings:
        """Update settings. Only provided keyword args are applied."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue_settings (channel_id)
                VALUES ($1)
                ON CONFLICT (channel_id) DO UPDATE SET
                    enabled              = COALESCE($2, video_queue_settings.enabled),
                    min_role_chat        = COALESCE($3, video_queue_settings.min_role_chat),
                    max_duration_seconds = COALESCE($4, video_queue_settings.max_duration_seconds),
                    max_queue_size       = COALESCE($5, video_queue_settings.max_queue_size)
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                enabled,
                min_role_chat,
                max_duration_seconds,
                max_queue_size,
            )
            result = VideoQueueSettings(**dict(row))
            _settings_cache.invalidate(f"vq_settings:{channel_id}")
            return result
