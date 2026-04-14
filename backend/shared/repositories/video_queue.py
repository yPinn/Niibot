"""Repository for video_queue and video_queue_settings tables.

Also contains shared utilities:
  - extract_youtube_id(): pure string parsing, used by bot and channel_points
  - fetch_yt_info(): YouTube Data API v3 call, used by bot and channel_points
  - extract_twitch_clip_slug(): pure string parsing for Twitch clip URLs
  - fetch_twitch_clip_info(): Twitch Helix API call for clip metadata
"""

from __future__ import annotations

import logging
import re
import time
from datetime import timedelta

import aiohttp
import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.video_queue import VideoQueueEntry, VideoQueueSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YouTube utilities
# ---------------------------------------------------------------------------

_YT_SHORTS_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})")

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


def extract_youtube_info(text: str) -> tuple[str | None, bool]:
    """Extract YouTube video ID and whether the URL is a Short (vertical video).

    Returns:
        (video_id, is_vertical) — video_id is None if no match found.
    """
    if _YT_SHORTS_RE.search(text):
        m = _YT_RE.search(text)
        return (m.group(1) if m else None, True)
    m = _YT_RE.search(text)
    return (m.group(1) if m else None, False)


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
) -> tuple[str | None, int | None, int | None, bool]:
    """Fetch video title, duration, view count, and orientation via YouTube Data API v3.

    If `session` is None a temporary one-shot session is created and closed.
    Returns (title, duration_seconds, view_count, is_vertical).
    is_vertical is True when the API reports portrait thumbnails (e.g. YouTube Shorts).
    title/duration/view_count are None on any failure; is_vertical defaults to False.
    """
    if not api_key:
        return None, None, None, False

    url = "https://www.googleapis.com/youtube/v3/videos"
    # Pass api_key via params dict so it never appears as a literal URL string
    # (prevents accidental key exposure in logs, traces, or error messages).
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": video_id,
        "key": api_key,
    }
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                logger.warning(f"[YouTube API] Unexpected status {resp.status} for {video_id}")
                return None, None, None, False
            data = await resp.json()
            items = data.get("items", [])
            if not items:
                return None, None, None, False  # video not found / private
            item = items[0]
            title: str | None = item.get("snippet", {}).get("title")
            raw_duration: str = item.get("contentDetails", {}).get("duration", "")
            duration_seconds = _parse_iso8601_duration(raw_duration) if raw_duration else 0
            raw_views: str | None = item.get("statistics", {}).get("viewCount")
            view_count = int(raw_views) if raw_views else None
            # Detect portrait orientation from thumbnail dimensions (Shorts have h > w)
            thumbnails: dict = item.get("snippet", {}).get("thumbnails", {})
            is_vertical = any(
                (t.get("height", 0) or 0) > (t.get("width", 1) or 1) for t in thumbnails.values()
            )
            return title, duration_seconds or None, view_count, is_vertical
    except Exception as exc:
        logger.warning(f"[YouTube API] fetch_yt_info failed for {video_id}: {type(exc).__name__}")
        return None, None, None, False
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Twitch Clip utilities
# ---------------------------------------------------------------------------

_TWITCH_CLIP_RE = re.compile(
    r"(?:https?://)?(?:clips\.twitch\.tv/|www\.twitch\.tv/\w+/clip/)([A-Za-z0-9_-]+)"
)

_TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
_TWITCH_HELIX_CLIPS_URL = "https://api.twitch.tv/helix/clips"

# Module-level app token cache keyed by (client_id, client_secret).
# Twitch app tokens are valid for ~60 days; we refresh 5 min before expiry.
_app_token_cache: dict[tuple[str, str], tuple[str, float]] = {}  # key → (token, expires_at)


def extract_twitch_clip_slug(text: str) -> str | None:
    """Extract clip slug from a Twitch clip URL. Returns None if not found.

    Supports:
      - https://clips.twitch.tv/{slug}
      - https://www.twitch.tv/{channel}/clip/{slug}
    """
    m = _TWITCH_CLIP_RE.search(text)
    return m.group(1) if m else None


async def _get_twitch_app_token(
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession,
) -> str | None:
    """Return a cached Twitch app token, fetching a new one only when expired.

    Tokens are valid ~60 days; we treat them as expired 5 min before their
    reported ``expires_in`` to guard against clock skew.
    """
    cache_key = (client_id, client_secret)
    cached_token, expires_at = _app_token_cache.get(cache_key, (None, 0.0))
    if cached_token and time.monotonic() < expires_at:
        return cached_token

    async with session.post(
        _TWITCH_OAUTH_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=aiohttp.ClientTimeout(total=5),
    ) as resp:
        if resp.status != 200:
            logger.warning(f"[Twitch API] Failed to get app token: {resp.status}")
            return None
        token_data = await resp.json()

    new_token = token_data.get("access_token")
    if not new_token:
        return None

    expires_in = token_data.get("expires_in", 3600)
    _app_token_cache[cache_key] = (new_token, time.monotonic() + expires_in - 300)
    return new_token


async def fetch_twitch_clip_info(
    slug: str,
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, int | None, int | None]:
    """Fetch clip title, duration, and view count via Twitch Helix API.

    Reuses a cached app access token (valid ~60 days); only fetches a new
    token when the cached one is missing or within 5 min of expiry.
    Returns (title, duration_seconds, view_count).
    All values are None on any failure.
    """
    if not client_id or not client_secret:
        return None, None, None

    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        app_token = await _get_twitch_app_token(client_id, client_secret, _session)
        if not app_token:
            return None, None, None

        # Fetch clip metadata
        async with _session.get(
            _TWITCH_HELIX_CLIPS_URL,
            params={"id": slug},
            headers={"Authorization": f"Bearer {app_token}", "Client-Id": client_id},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                logger.warning(f"[Twitch API] Unexpected status {resp.status} for clip {slug}")
                return None, None, None
            data = await resp.json()
            clips = data.get("data", [])
            if not clips:
                return None, None, None  # clip not found or deleted
            clip = clips[0]
            title: str | None = clip.get("title")
            duration_raw = clip.get("duration")
            duration_seconds = int(round(float(duration_raw))) if duration_raw is not None else None
            view_count_raw = clip.get("view_count")
            view_count = int(view_count_raw) if view_count_raw is not None else None
            return title, duration_seconds, view_count
    except Exception as exc:
        logger.warning(
            f"[Twitch API] fetch_twitch_clip_info failed for {slug}: {type(exc).__name__}"
        )
        return None, None, None
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Priority constants
# ---------------------------------------------------------------------------

# Maps each submission source to its queue priority tier.
# Higher value = plays before lower value entries within the same channel.
# Same-tier entries are served FIFO (ORDER BY created_at ASC).
SOURCE_PRIORITY: dict[str, int] = {
    "chat": 0,
    "redemption": 10,
    "donation": 20,  # reserved for future payment platform integration
    "dashboard": 30,
}

# Internal priority used by set_as_next to pin an entry above all normal tiers.
PRIORITY_PINNED = 99

# ---------------------------------------------------------------------------
# Column constants
# ---------------------------------------------------------------------------

_ENTRY_COLUMNS = (
    "id, channel_id, video_id, title, duration_seconds, is_vertical, requested_by, "
    "source, status, video_type, priority, created_at, started_at, requested_by_id"
)

_SETTINGS_COLUMNS = (
    "channel_id, enabled, redemption_enabled, "
    "max_duration_redemption, max_queue_size, "
    "min_view_count, user_cooldown_seconds, max_per_user, "
    "created_at, updated_at"
)

_settings_cache = AsyncTTLCache(maxsize=32, ttl=15)


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
        is_vertical: bool = False,
        video_type: str = "youtube",
        priority: int = 0,
        requested_by_id: str | None = None,
    ) -> VideoQueueEntry:
        """Insert a new entry with status='queued'."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue
                    (channel_id, video_id, title, duration_seconds, is_vertical,
                     requested_by, source, video_type, priority, requested_by_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING {_ENTRY_COLUMNS}
                """,
                channel_id,
                video_id,
                title,
                duration_seconds,
                is_vertical,
                requested_by,
                source,
                video_type,
                priority,
                requested_by_id,
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
        """Return all queued (not yet playing) entries ordered by priority DESC, created_at ASC."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                "WHERE channel_id = $1 AND status = 'queued' "
                "ORDER BY priority DESC, created_at ASC",
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

    async def update_duration(self, entry_id: int, duration_seconds: int, channel_id: str) -> None:
        """Update duration_seconds (overlay fallback report after load). Scoped to channel."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET duration_seconds = $2 WHERE id = $1 AND channel_id = $3",
                entry_id,
                duration_seconds,
                channel_id,
            )

    async def mark_done(self, entry_id: int, channel_id: str) -> None:
        """Transition entry to 'done'. Only applies when status='playing' and entry belongs to channel."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET status = 'done', ended_at = NOW() "
                "WHERE id = $1 AND channel_id = $2 AND status = 'playing'",
                entry_id,
                channel_id,
            )

    async def advance_queue(self, channel_id: str, done_id: int) -> None:
        """Atomically mark done_id as done and promote the next queued entry to playing.

        Both operations run inside a single transaction to prevent a race condition
        where concurrent advance calls could promote the same entry twice. Follows
        the same transaction pattern as play_immediately.

        If no queued entry exists after marking done, the second UPDATE is a no-op.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE video_queue SET status = 'done', ended_at = NOW() "
                    "WHERE id = $1 AND channel_id = $2 AND status = 'playing'",
                    done_id,
                    channel_id,
                )
                await conn.execute(
                    "UPDATE video_queue "
                    "SET status = 'playing', started_at = NOW() "
                    "WHERE id = ("
                    "    SELECT id FROM video_queue "
                    "    WHERE channel_id = $1 AND status = 'queued' "
                    "    ORDER BY priority DESC, created_at ASC LIMIT 1"
                    ")",
                    channel_id,
                )

    async def mark_skipped(self, entry_id: int, channel_id: str) -> None:
        """Transition entry to 'skipped'. Only applies to entries owned by the channel."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                "WHERE id = $1 AND channel_id = $2 AND status IN ('queued', 'playing')",
                entry_id,
                channel_id,
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

    async def clear_all_atomic(self, channel_id: str) -> int:
        """Atomically skip all playing and queued entries in a single statement.

        Using a single UPDATE avoids the race where advance_queue (triggered by
        the overlay between two separate calls) promotes a queued entry to
        'playing' after the playing entry has already been skipped but before
        clear_queued runs — which would leave that entry un-cleared.

        Returns total count of affected rows.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                "WHERE channel_id = $1 AND status IN ('playing', 'queued')",
                channel_id,
            )
            return int(result.split()[-1])

    async def set_as_next(self, entry_id: int, channel_id: str) -> bool:
        """Move a queued entry to the absolute front of the queue (plays after current).

        Sets priority = PRIORITY_PINNED (99) to ensure the entry floats above all
        normal-tier entries regardless of source. Also adjusts created_at to be
        1 second before the current minimum among all queued entries, so multiple
        consecutive set_as_next calls produce a stable "most-recently-pinned plays
        first" order within the PRIORITY_PINNED tier.
        Returns True if the entry was found and updated.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                min_ts = await conn.fetchval(
                    "SELECT MIN(created_at) FROM video_queue "
                    "WHERE channel_id = $1 AND status = 'queued' AND id != $2",
                    channel_id,
                    entry_id,
                )
                new_ts = (min_ts - timedelta(seconds=1)) if min_ts is not None else None
                result = await conn.execute(
                    # priority = PRIORITY_PINNED overrides all source-based tiers.
                    # created_at is pushed before all others so the most-recently-pinned
                    # entry always sorts first within the pinned tier.
                    "UPDATE video_queue "
                    "SET priority = $4, "
                    "    created_at = COALESCE($3, NOW() - INTERVAL '10 years') "
                    "WHERE id = $1 AND channel_id = $2 AND status = 'queued'",
                    entry_id,
                    channel_id,
                    new_ts,
                    PRIORITY_PINNED,
                )
                return result == "UPDATE 1"

    async def skip_current_atomic(self, channel_id: str) -> None:
        """Atomically mark the current playing entry as skipped and promote the next queued entry.

        Both operations run inside a single transaction to prevent a race condition
        where a concurrent advance_queue call (from the overlay) could promote the
        same queued entry while the dashboard skip is in flight.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                    "WHERE channel_id = $1 AND status = 'playing'",
                    channel_id,
                )
                await conn.execute(
                    "UPDATE video_queue "
                    "SET status = 'playing', started_at = NOW() "
                    "WHERE id = ("
                    "    SELECT id FROM video_queue "
                    "    WHERE channel_id = $1 AND status = 'queued' "
                    "    ORDER BY priority DESC, created_at ASC LIMIT 1"
                    ")",
                    channel_id,
                )

    async def play_immediately(self, entry_id: int, channel_id: str) -> bool:
        """Skip the currently playing video and start playing this entry immediately.

        1. Marks any 'playing' entry as 'skipped'.
        2. Transitions this entry from 'queued' to 'playing'.

        Returns True if the entry was promoted, False if it was not found or not queued.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Skip current playing entry (if any)
                await conn.execute(
                    "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                    "WHERE channel_id = $1 AND status = 'playing'",
                    channel_id,
                )
                # Start playing the requested entry
                result = await conn.execute(
                    "UPDATE video_queue "
                    "SET status = 'playing', started_at = NOW() "
                    "WHERE id = $1 AND channel_id = $2 AND status = 'queued'",
                    entry_id,
                    channel_id,
                )
                return result == "UPDATE 1"

    async def count_active_by_user(
        self,
        channel_id: str,
        requested_by: str,
        requested_by_id: str | None = None,
    ) -> int:
        """Count active (queued + playing) entries for a specific user in this channel.

        Matches by user_id when available (resilient to username changes),
        falling back to username for legacy rows.
        """
        async with self.pool.acquire() as conn:
            if requested_by_id:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM video_queue "
                    "WHERE channel_id = $1 AND status IN ('queued', 'playing') "
                    "AND (requested_by_id = $2 OR (requested_by_id IS NULL AND requested_by = $3))",
                    channel_id,
                    requested_by_id,
                    requested_by,
                )
            return await conn.fetchval(
                "SELECT COUNT(*) FROM video_queue "
                "WHERE channel_id = $1 AND requested_by = $2 AND status IN ('queued', 'playing')",
                channel_id,
                requested_by,
            )

    async def find_last_queued_by_user(
        self,
        channel_id: str,
        requested_by: str,
        requested_by_id: str | None = None,
    ) -> VideoQueueEntry | None:
        """Find the most recently submitted queued entry for a given user (for !vq remove).

        Matches by user_id when available, falling back to username for legacy rows.
        """
        async with self.pool.acquire() as conn:
            if requested_by_id:
                row = await conn.fetchrow(
                    f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                    "WHERE channel_id = $1 AND status = 'queued' "
                    "AND (requested_by_id = $2 OR (requested_by_id IS NULL AND requested_by = $3)) "
                    "ORDER BY created_at DESC LIMIT 1",
                    channel_id,
                    requested_by_id,
                    requested_by,
                )
            else:
                row = await conn.fetchrow(
                    f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                    "WHERE channel_id = $1 AND requested_by = $2 AND status = 'queued' "
                    "ORDER BY created_at DESC LIMIT 1",
                    channel_id,
                    requested_by,
                )
            return VideoQueueEntry(**dict(row)) if row else None

    async def find_last_entry_by_user(
        self,
        channel_id: str,
        requested_by: str,
        requested_by_id: str | None = None,
    ) -> VideoQueueEntry | None:
        """Find the most recently submitted entry for a given user regardless of status.

        Used for user_cooldown_seconds enforcement — we want the last submission
        time across all statuses (queued, playing, done, skipped).
        Matches by user_id when available, falling back to username for legacy rows.
        """
        async with self.pool.acquire() as conn:
            if requested_by_id:
                row = await conn.fetchrow(
                    f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                    "WHERE channel_id = $1 "
                    "AND (requested_by_id = $2 OR (requested_by_id IS NULL AND requested_by = $3)) "
                    "ORDER BY created_at DESC LIMIT 1",
                    channel_id,
                    requested_by_id,
                    requested_by,
                )
            else:
                row = await conn.fetchrow(
                    f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                    "WHERE channel_id = $1 AND requested_by = $2 "
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
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO video_queue_settings (channel_id) VALUES ($1) ON CONFLICT DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"SELECT {_SETTINGS_COLUMNS} FROM video_queue_settings WHERE channel_id = $1",
                    channel_id,
                )
            return VideoQueueSettings(**dict(row))

    async def update_settings(
        self,
        channel_id: str,
        *,
        enabled: bool | None = None,
        redemption_enabled: bool | None = None,
        max_duration_redemption: int | None = None,
        max_queue_size: int | None = None,
        min_view_count: int | None = None,
        user_cooldown_seconds: int | None = None,
        max_per_user: int | None = None,
    ) -> VideoQueueSettings:
        """Update settings. Only provided keyword args are applied."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue_settings (channel_id)
                VALUES ($1)
                ON CONFLICT (channel_id) DO UPDATE SET
                    enabled                  = COALESCE($2, video_queue_settings.enabled),
                    redemption_enabled       = COALESCE($3, video_queue_settings.redemption_enabled),
                    max_duration_redemption  = COALESCE($4, video_queue_settings.max_duration_redemption),
                    max_queue_size           = COALESCE($5, video_queue_settings.max_queue_size),
                    min_view_count           = COALESCE($6, video_queue_settings.min_view_count),
                    user_cooldown_seconds    = COALESCE($7, video_queue_settings.user_cooldown_seconds),
                    max_per_user             = COALESCE($8, video_queue_settings.max_per_user)
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                enabled,
                redemption_enabled,
                max_duration_redemption,
                max_queue_size,
                min_view_count,
                user_cooldown_seconds,
                max_per_user,
            )
            result = VideoQueueSettings(**dict(row))
            _settings_cache.invalidate(f"vq_settings:{channel_id}")
            return result
