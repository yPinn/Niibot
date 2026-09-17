"""Repository for the video_queue and video_queue_settings tables.

Video-source URL parsing and metadata fetching (YouTube / Bilibili / Twitch
clips) live in ``shared.video_sources``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.video_queue import (
    VideoQueueBlocklistEntry,
    VideoQueueEntry,
    VideoQueueSettings,
)
from shared.video_sources import build_watch_url

LOGGER: logging.Logger = logging.getLogger(__name__)


def format_now_playing(entry: VideoQueueEntry) -> str:
    """Render the !np chat line for the currently playing entry.

    No remaining time: it is stale the moment the message is sent, and a
    viewer reading it seconds later is told the wrong number. The overlay
    already shows a live countdown for anyone who needs one.
    """
    url = build_watch_url(entry.video_type, entry.video_id)
    title_part = f"「{entry.title}」 " if entry.title else " "
    return f"▶{title_part}{url} | 點播者：{entry.requested_by}"


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
    "id, channel_id, video_id, title, duration_seconds, is_vertical, thumbnail_url, start_seconds, "
    "requested_by, source, status, video_type, priority, "
    "created_at, started_at, ended_at, requested_by_id, creator_id, creator_name"
)

# History = terminal entries retained for the dashboard "played" tab.
HISTORY_STATUSES = ("done", "skipped")
HISTORY_RETENTION_DAYS = 30

_SETTINGS_COLUMNS = (
    "channel_id, enabled, redemption_enabled, "
    "max_duration_redemption, max_queue_size, "
    "min_view_count, user_cooldown_seconds, max_per_user, "
    "max_duration_seconds, replay_cooldown_hours, "
    "created_at, updated_at"
)

_settings_cache = AsyncTTLCache(maxsize=32, ttl=15, name="video_queue.settings")

_BLOCKLIST_COLUMNS = "id, channel_id, kind, value, label, created_by, created_at"

BLOCKLIST_KINDS = ("video", "creator", "keyword", "user")

# Per-channel cache of the full blocklist, refreshed on write. The check runs on
# every submission (three add paths) and the list is tiny, so we match in Python
# rather than issue a query per add.
_blocklist_cache = AsyncTTLCache(maxsize=64, ttl=30, name="video_queue.blocklist")


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
        start_seconds: int = 0,
        thumbnail_url: str | None = None,
        creator_id: str | None = None,
        creator_name: str | None = None,
    ) -> VideoQueueEntry:
        """Insert a new entry with status='queued'."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue
                    (channel_id, video_id, title, duration_seconds, is_vertical, start_seconds,
                     requested_by, source, video_type, priority, requested_by_id, thumbnail_url,
                     creator_id, creator_name)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING {_ENTRY_COLUMNS}
                """,
                channel_id,
                video_id,
                title,
                duration_seconds,
                is_vertical,
                start_seconds,
                requested_by,
                source,
                video_type,
                priority,
                requested_by_id,
                thumbnail_url,
                creator_id,
                creator_name,
            )
            return VideoQueueEntry(**dict(row))

    async def add_if_within_limits(
        self,
        channel_id: str,
        video_id: str,
        requested_by: str,
        source: str,
        *,
        max_queue_size: int,
        max_per_user: int,
        requested_by_id: str | None = None,
        title: str | None = None,
        duration_seconds: int | None = None,
        is_vertical: bool = False,
        video_type: str = "youtube",
        priority: int = 0,
        start_seconds: int = 0,
        thumbnail_url: str | None = None,
        creator_id: str | None = None,
        creator_name: str | None = None,
    ) -> VideoQueueEntry | None:
        """Re-validate duplicate/queue-size/per-user limits and insert atomically.

        Callers typically pre-check these same limits before doing slow I/O
        (fetching video metadata), for a fast, specific rejection message.
        But that check and this insert are seconds apart, so two concurrent
        requests can both pass the pre-check before either row exists. This
        method closes that gap: a transaction-scoped advisory lock keyed on
        channel_id serializes concurrent adds for the same channel, and the
        limits are re-checked inside that same transaction immediately before
        the INSERT. Returns None if any limit is exceeded at insert time —
        callers should fall back to a generic "queue changed, try again"
        message in that (rare) case.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", channel_id
                )

                # One query for all three limits — minimizes time held under the lock.
                counts = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) FILTER (
                            WHERE video_id = $2 AND status IN ('queued', 'playing')
                        ) AS duplicate_count,
                        COUNT(*) FILTER (WHERE status = 'queued') AS queue_size,
                        COUNT(*) FILTER (
                            WHERE status IN ('queued', 'playing')
                            AND CASE
                                WHEN $3::text IS NOT NULL THEN
                                    requested_by_id = $3
                                    OR (requested_by_id IS NULL AND requested_by = $4)
                                ELSE
                                    requested_by = $4
                            END
                        ) AS user_count
                    FROM video_queue
                    WHERE channel_id = $1
                    """,
                    channel_id,
                    video_id,
                    requested_by_id,
                    requested_by,
                )
                if counts["duplicate_count"] > 0:
                    return None
                if counts["queue_size"] >= max_queue_size:
                    return None
                if max_per_user > 0 and counts["user_count"] >= max_per_user:
                    return None

                row = await conn.fetchrow(
                    f"""
                    INSERT INTO video_queue
                        (channel_id, video_id, title, duration_seconds, is_vertical, start_seconds,
                         requested_by, source, video_type, priority, requested_by_id, thumbnail_url,
                         creator_id, creator_name)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    RETURNING {_ENTRY_COLUMNS}
                    """,
                    channel_id,
                    video_id,
                    title,
                    duration_seconds,
                    is_vertical,
                    start_seconds,
                    requested_by,
                    source,
                    video_type,
                    priority,
                    requested_by_id,
                    thumbnail_url,
                    creator_id,
                    creator_name,
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

    async def get_current_and_queued(
        self, channel_id: str
    ) -> tuple[VideoQueueEntry | None, list[VideoQueueEntry]]:
        """Single-connection read combining get_current + get_queued.

        Used by the stream wake path instead of asyncio.gather-ing get_current
        and get_queued as separate pool.acquire()s: the API pool is small
        (max_size=3) and a NOTIFY wake can fan out to up to
        max_subscribers_per_channel overlays at once, each of which would
        otherwise acquire 2 connections simultaneously.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                "WHERE channel_id = $1 AND status IN ('queued', 'playing') "
                "ORDER BY CASE status WHEN 'playing' THEN 0 ELSE 1 END, "
                "started_at ASC, priority DESC, created_at ASC",
                channel_id,
            )
        current: VideoQueueEntry | None = None
        queued: list[VideoQueueEntry] = []
        for row in rows:
            entry = VideoQueueEntry(**dict(row))
            if entry.status == "playing":
                if current is None:  # tolerate a stale duplicate rather than crash
                    current = entry
            else:
                queued.append(entry)
        return current, queued

    async def get_queue_size(self, channel_id: str) -> int:
        """Count entries with status='queued'."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM video_queue WHERE channel_id = $1 AND status = 'queued'",
                channel_id,
            )

    async def get_entry_for_channel(self, entry_id: int, channel_id: str) -> VideoQueueEntry | None:
        """Fetch a single entry scoped to its channel, any status."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue WHERE id = $1 AND channel_id = $2",
                entry_id,
                channel_id,
            )
            return VideoQueueEntry(**dict(row)) if row else None

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

    async def kickstart_if_idle(self, channel_id: str) -> None:
        """Atomically promote the next queued entry to playing only if nothing is currently playing."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue "
                "SET status = 'playing', started_at = NOW() "
                "WHERE id = ("
                "    SELECT id FROM video_queue "
                "    WHERE channel_id = $1 AND status = 'queued' "
                "    AND NOT EXISTS ("
                "        SELECT 1 FROM video_queue WHERE channel_id = $1 AND status = 'playing'"
                "    ) "
                "    ORDER BY priority DESC, created_at ASC LIMIT 1"
                ")",
                channel_id,
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

        The promote UPDATE also requires NOT EXISTS(status='playing') — same guard
        as kickstart_if_idle. Without it, two overlays finishing the same done_id
        concurrently (or an overlay finishing while a dashboard Play-Now runs) can
        both have their first UPDATE match zero rows and their second UPDATE
        unconditionally promote a queued entry, leaving two rows 'playing' at once.
        That state is permanent: get_current only ever returns one of them, and
        kickstart_if_idle's own NOT EXISTS guard then stays false until the queue
        is cleared.
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
                    "    AND NOT EXISTS ("
                    "        SELECT 1 FROM video_queue WHERE channel_id = $1 AND status = 'playing'"
                    "    ) "
                    "    ORDER BY priority DESC, created_at ASC LIMIT 1"
                    ")",
                    channel_id,
                )

    async def mark_skipped(self, entry_id: int, channel_id: str) -> bool:
        """Transition entry to 'skipped'. Returns True if a row was affected."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW() "
                "WHERE id = $1 AND channel_id = $2 AND status IN ('queued', 'playing')",
                entry_id,
                channel_id,
            )
            return int(result.split()[-1]) > 0

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

    async def get_history(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[VideoQueueEntry]:
        """Terminal entries (done/skipped) for this channel, newest first.

        ``before`` is a keyset cursor on ``ended_at`` — pass the ``ended_at`` of
        the last row from the previous page to fetch the next one.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_ENTRY_COLUMNS} FROM video_queue "
                "WHERE channel_id = $1 AND status = ANY($2) AND ended_at IS NOT NULL "
                "AND ($3::timestamptz IS NULL OR ended_at < $3) "
                "ORDER BY ended_at DESC LIMIT $4",
                channel_id,
                list(HISTORY_STATUSES),
                before,
                limit,
            )
            return [VideoQueueEntry(**dict(row)) for row in rows]

    async def played_within(self, channel_id: str, video_id: str, hours: int) -> bool:
        """True if this video finished playing (``status = 'done'``) within the
        last ``hours`` in this channel — the replay-cooldown check."""
        async with self.pool.acquire() as conn:
            found = await conn.fetchval(
                "SELECT 1 FROM video_queue "
                "WHERE channel_id = $1 AND video_id = $2 AND status = 'done' "
                "AND ended_at IS NOT NULL AND ended_at > NOW() - make_interval(hours => $3) "
                "LIMIT 1",
                channel_id,
                video_id,
                hours,
            )
            return found is not None

    async def prune_history(self) -> int:
        """Delete history rows past the retention window. Returns rows removed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM video_queue "
                "WHERE status = ANY($1) AND ended_at IS NOT NULL "
                "AND ended_at < NOW() - make_interval(days => $2)",
                list(HISTORY_STATUSES),
                HISTORY_RETENTION_DAYS,
            )
            return int(result.split()[-1]) if result.startswith("DELETE") else 0


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
        max_duration_seconds: int | None = None,
        replay_cooldown_hours: int | None = None,
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
                    max_per_user             = COALESCE($8, video_queue_settings.max_per_user),
                    max_duration_seconds     = COALESCE($9, video_queue_settings.max_duration_seconds),
                    replay_cooldown_hours    = COALESCE($10, video_queue_settings.replay_cooldown_hours)
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
                max_duration_seconds,
                replay_cooldown_hours,
            )
            result = VideoQueueSettings(**dict(row))
            _settings_cache.invalidate(f"vq_settings:{channel_id}")
            return result


# ---------------------------------------------------------------------------
# VideoQueueBlocklistRepository
# ---------------------------------------------------------------------------


def _blocklist_match(
    entries: list[VideoQueueBlocklistEntry],
    *,
    video_id: str,
    title: str | None,
    requested_by: str | None,
    requested_by_id: str | None,
    creator_id: str | None,
) -> VideoQueueBlocklistEntry | None:
    """First blocklist rule a submission trips, or None. Case-insensitive.

    ``creator`` matches the platform-native ``creator_id`` (channel/uploader/
    broadcaster identity — see migration 122), not ``video_id``. A submission
    whose metadata fetch couldn't resolve a creator_id (transient failure, or
    a platform this integration doesn't capture it for) simply never trips a
    ``creator`` rule — same fail-open posture as every other best-effort
    metadata field here.
    """
    title_l = (title or "").lower()
    login_l = (requested_by or "").lower()
    creator_l = (creator_id or "").lower()
    for entry in entries:
        value_l = entry.value.lower()
        if entry.kind == "video" and value_l == video_id.lower():
            return entry
        if entry.kind == "creator" and creator_l and value_l == creator_l:
            return entry
        if entry.kind == "keyword" and title_l and value_l in title_l:
            return entry
        if entry.kind == "user" and (
            (login_l and value_l == login_l)
            or (requested_by_id is not None and entry.value == requested_by_id)
        ):
            return entry
    return None


class VideoQueueBlocklistRepository:
    """Pure SQL operations for the video_queue_blocklist table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_entries(self, channel_id: str) -> list[VideoQueueBlocklistEntry]:
        """All blocklist rules for a channel, newest first. Cached per channel."""
        if channel_id in _blocklist_cache:
            return _blocklist_cache.get(channel_id)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_BLOCKLIST_COLUMNS} FROM video_queue_blocklist "
                "WHERE channel_id = $1 ORDER BY created_at DESC",
                channel_id,
            )
        entries = [VideoQueueBlocklistEntry(**dict(row)) for row in rows]
        _blocklist_cache.set(channel_id, entries)
        return entries

    async def add(
        self,
        channel_id: str,
        kind: str,
        value: str,
        *,
        label: str | None = None,
        created_by: str | None = None,
    ) -> VideoQueueBlocklistEntry:
        """Insert a rule, or return the existing one for the same (channel, kind, value)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue_blocklist (channel_id, kind, value, label, created_by)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (channel_id, kind, lower(value)) DO UPDATE SET
                    label = COALESCE(EXCLUDED.label, video_queue_blocklist.label)
                RETURNING {_BLOCKLIST_COLUMNS}
                """,
                channel_id,
                kind,
                value,
                label,
                created_by,
            )
        _blocklist_cache.invalidate(channel_id)
        return VideoQueueBlocklistEntry(**dict(row))

    async def remove(self, channel_id: str, entry_id: int) -> bool:
        """Delete a rule scoped to its channel. Returns True if a row was removed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM video_queue_blocklist WHERE id = $1 AND channel_id = $2",
                entry_id,
                channel_id,
            )
        _blocklist_cache.invalidate(channel_id)
        return int(result.split()[-1]) > 0

    async def check(
        self,
        channel_id: str,
        *,
        video_id: str,
        title: str | None = None,
        requested_by: str | None = None,
        requested_by_id: str | None = None,
        creator_id: str | None = None,
    ) -> VideoQueueBlocklistEntry | None:
        """Return the first blocklist rule this submission trips, or None."""
        entries = await self.list_entries(channel_id)
        if not entries:
            return None
        return _blocklist_match(
            entries,
            video_id=video_id,
            title=title,
            requested_by=requested_by,
            requested_by_id=requested_by_id,
            creator_id=creator_id,
        )
