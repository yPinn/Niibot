"""Repository for the video_queue and video_queue_settings tables.

Video-source URL parsing and metadata fetching (YouTube / Bilibili / Twitch
clips) live in ``shared.video_sources``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.video_queue import (
    VideoQueueBlocklistEntry,
    VideoQueueEntry,
    VideoQueueInsert,
    VideoQueueRankingEntry,
    VideoQueueSettings,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkipResult:
    """Outcome of ``skip_current_atomic``.

    ``skipped`` is False only for a conditional skip whose expected entry was
    no longer the one playing; ``next_entry`` is the row actually promoted.
    """

    skipped: bool
    next_entry: VideoQueueEntry | None = None


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
    "created_at, started_at, ended_at, requested_by_id, creator_id, creator_name, "
    "playback_started_at, playback_signal, end_reason, played_seconds"
)

# History = terminal entries retained for the dashboard "played" tab.
HISTORY_STATUSES = ("done", "skipped")
HISTORY_RETENTION_DAYS = 30

_SETTINGS_COLUMNS = (
    "channel_id, overlay_key, enabled, redemption_enabled, "
    "max_duration_redemption, max_queue_size, "
    "min_view_count, user_cooldown_seconds, max_per_user, "
    "max_duration_seconds, replay_cooldown_hours, volume_percent, "
    "insert_audio_only, "
    "created_at, updated_at"
)

_INSERT_COLUMNS = (
    "id, channel_id, source_type, source_id, title, creator_id, creator_name, "
    "thumbnail_url, volume_percent, audio_only, started_at"
)

# A live insert plays in the background whenever the queue is empty. It counts
# as active for this long after it started — a forgotten insert must not
# resume on the next broadcast.
INSERT_MAX_HOURS = 12

_settings_cache = AsyncTTLCache(maxsize=32, ttl=15, name="video_queue.settings")

_BLOCKLIST_COLUMNS = "id, channel_id, kind, video_type, value, label, created_by, created_at"

BLOCKLIST_KINDS = ("video", "creator", "keyword", "user")
VIDEO_TYPES = ("youtube", "twitch_clip", "twitch_vod", "bilibili", "instagram_reel")
PLAYBACK_SIGNALS = ("confirmed", "best_effort")
END_REASONS = (
    "completed",
    "provider_error",
    "autoplay_blocked",
    "startup_timeout",
    "dashboard_skip",
    "chat_skip",
    "play_now",
    "removed",
    "cleared",
)

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
                            WHERE video_id = $2 AND video_type = $5
                            AND status IN ('queued', 'playing')
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
                    video_type,
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

    async def get_stream_snapshot(
        self, channel_id: str
    ) -> tuple[VideoQueueEntry | None, list[VideoQueueEntry], VideoQueueInsert | None]:
        """Current + queued + active live insert, on one connection (see below)."""
        async with self.pool.acquire() as conn:
            current, queued = await self._current_and_queued(conn, channel_id)
            insert = await _fetch_active_insert(conn, channel_id)
        return current, queued, insert

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
            return await self._current_and_queued(conn, channel_id)

    @staticmethod
    async def _current_and_queued(
        conn: asyncpg.Connection, channel_id: str
    ) -> tuple[VideoQueueEntry | None, list[VideoQueueEntry]]:
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

    async def video_is_active(
        self, channel_id: str, video_id: str, video_type: str = "youtube"
    ) -> bool:
        """Return whether this provider-native identity is queued or playing."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM video_queue "
                "WHERE channel_id = $1 AND video_id = $2 AND video_type = $3 "
                "AND status IN ('queued', 'playing')",
                channel_id,
                video_id,
                video_type,
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

    async def mark_playback_started(self, entry_id: int, channel_id: str, signal: str) -> bool:
        """Record one qualified playback fact for the current entry.

        The write is idempotent across overlay reconnects. A later controlled
        player event may upgrade an earlier iframe-style best-effort signal,
        but never move the original start timestamp.
        """
        if signal not in PLAYBACK_SIGNALS:
            raise ValueError(f"Unsupported playback signal: {signal}")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE video_queue "
                "SET playback_started_at = COALESCE(playback_started_at, NOW()), "
                "    playback_signal = CASE "
                "        WHEN playback_signal = 'confirmed' THEN playback_signal "
                "        ELSE $3 "
                "    END "
                "WHERE id = $1 AND channel_id = $2 AND status = 'playing'",
                entry_id,
                channel_id,
                signal,
            )
        return result == "UPDATE 1"

    async def mark_done(self, entry_id: int, channel_id: str) -> None:
        """Transition entry to 'done'. Only applies when status='playing' and entry belongs to channel."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue SET status = 'done', ended_at = NOW(), "
                "end_reason = 'completed', "
                "played_seconds = CASE WHEN playback_started_at IS NULL THEN NULL ELSE "
                "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - playback_started_at)))::integer) END "
                "WHERE id = $1 AND channel_id = $2 AND status = 'playing'",
                entry_id,
                channel_id,
            )

    async def advance_queue(
        self, channel_id: str, done_id: int, *, end_reason: str = "completed"
    ) -> None:
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
        if end_reason not in END_REASONS:
            raise ValueError(f"Unsupported end reason: {end_reason}")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE video_queue SET status = 'done', ended_at = NOW(), "
                    "end_reason = $3, "
                    "played_seconds = CASE WHEN playback_started_at IS NULL THEN NULL ELSE "
                    "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - playback_started_at)))::integer) END "
                    "WHERE id = $1 AND channel_id = $2 AND status = 'playing'",
                    done_id,
                    channel_id,
                    end_reason,
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
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW(), "
                "end_reason = 'removed', "
                "played_seconds = CASE WHEN playback_started_at IS NULL THEN NULL ELSE "
                "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - playback_started_at)))::integer) END "
                "WHERE id = $1 AND channel_id = $2 AND status IN ('queued', 'playing')",
                entry_id,
                channel_id,
            )
            return int(result.split()[-1]) > 0

    async def clear_queued(self, channel_id: str) -> int:
        """Mark all queued entries as skipped. Returns count of affected rows."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW(), end_reason = 'cleared' "
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
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW(), "
                "end_reason = 'cleared', "
                "played_seconds = CASE WHEN playback_started_at IS NULL THEN NULL ELSE "
                "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - playback_started_at)))::integer) END "
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

    async def skip_current_atomic(
        self,
        channel_id: str,
        *,
        expected_entry_id: int | None = None,
        end_reason: str = "dashboard_skip",
    ) -> SkipResult:
        """Atomically mark the current playing entry as skipped and promote the next queued entry.

        Both operations run inside a single transaction to prevent a race condition
        where a concurrent advance_queue call (from the overlay) could promote the
        same queued entry while the skip is in flight.

        With ``expected_entry_id`` the skip is conditional: callers look up the
        current entry first, and the overlay may have advanced in between. Without
        the condition such a caller would skip the *next* video — someone else's
        request — so nothing changes and ``skipped`` is False instead.
        """
        if end_reason not in END_REASONS:
            raise ValueError(f"Unsupported end reason: {end_reason}")
        skip_sql = (
            "UPDATE video_queue SET status = 'skipped', ended_at = NOW(), "
            "end_reason = $2, "
            "played_seconds = CASE WHEN playback_started_at IS NULL THEN NULL ELSE "
            "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - playback_started_at)))::integer) END "
            "WHERE channel_id = $1 AND status = 'playing'"
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if expected_entry_id is None:
                    await conn.execute(skip_sql, channel_id, end_reason)
                else:
                    result = await conn.execute(
                        f"{skip_sql} AND id = $3", channel_id, end_reason, expected_entry_id
                    )
                    if int(result.split()[-1]) == 0:
                        return SkipResult(skipped=False)
                row = await conn.fetchrow(
                    "UPDATE video_queue "
                    "SET status = 'playing', started_at = NOW() "
                    "WHERE id = ("
                    "    SELECT id FROM video_queue "
                    "    WHERE channel_id = $1 AND status = 'queued' "
                    "    ORDER BY priority DESC, created_at ASC LIMIT 1"
                    f") RETURNING {_ENTRY_COLUMNS}",
                    channel_id,
                )
        return SkipResult(skipped=True, next_entry=VideoQueueEntry(**dict(row)) if row else None)

    async def get_queue_position(self, entry_id: int, channel_id: str) -> int | None:
        """1-based place of a queued entry in play order (priority DESC, created_at ASC).

        None when the entry is no longer queued (e.g. the overlay already
        promoted it to playing).
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM video_queue q, ("
                "    SELECT priority, created_at FROM video_queue "
                "    WHERE id = $1 AND channel_id = $2 AND status = 'queued'"
                ") e "
                "WHERE q.channel_id = $2 AND q.status = 'queued' "
                "AND (q.priority > e.priority "
                "     OR (q.priority = e.priority AND q.created_at <= e.created_at)) "
                "HAVING COUNT(*) > 0",
                entry_id,
                channel_id,
            )

    async def cancel_queued(self, entry_id: int, channel_id: str) -> bool:
        """Remove an entry only while it is still waiting (``!vq remove``).

        Unlike ``mark_skipped`` this never touches a playing row: a viewer
        cancelling their request must not end a video the overlay promoted in
        the meantime — that is ``!vq skip``'s job.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE video_queue SET status = 'skipped', ended_at = NOW(), "
                "end_reason = 'removed' "
                "WHERE id = $1 AND channel_id = $2 AND status = 'queued'",
                entry_id,
                channel_id,
            )
            return int(result.split()[-1]) > 0

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
                    "UPDATE video_queue SET status = 'skipped', ended_at = NOW(), "
                    "end_reason = 'play_now', "
                    "played_seconds = CASE WHEN playback_started_at IS NULL THEN NULL ELSE "
                    "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - playback_started_at)))::integer) END "
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

    async def get_rankings(
        self,
        channel_id: str,
        *,
        scope: str,
        days: int,
        video_type: str | None = None,
        limit: int = 50,
    ) -> list[VideoQueueRankingEntry]:
        """Return private, anonymous playback aggregates for the workbench.

        All filter values stay parameters in one static query. Besides keeping
        the SQL injection surface closed, this makes the privacy boundary
        obvious: requester and contributing-channel identities never leave
        the database.
        """
        if scope not in {"channel", "global"}:
            raise ValueError(f"Unsupported ranking scope: {scope}")
        if days not in {7, 30}:
            raise ValueError(f"Unsupported ranking window: {days}")
        if video_type is not None and video_type not in VIDEO_TYPES:
            raise ValueError(f"Unsupported video type: {video_type}")
        if not 1 <= limit <= 100:
            raise ValueError("Ranking limit must be between 1 and 100")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH qualified AS (
                    SELECT
                        channel_id,
                        video_type,
                        video_id,
                        start_seconds,
                        title,
                        thumbnail_url,
                        creator_id,
                        creator_name,
                        playback_started_at
                    FROM video_queue
                    WHERE playback_started_at IS NOT NULL
                      AND playback_started_at >= NOW() - make_interval(days => $2)
                      AND ($3::text IS NULL OR video_type = $3)
                      AND ($4::text = 'global' OR channel_id = $1)
                ), aggregated AS (
                    SELECT
                        video_type,
                        video_id,
                        (ARRAY_AGG(start_seconds ORDER BY playback_started_at DESC))[1]
                            AS start_seconds,
                        (ARRAY_AGG(title ORDER BY playback_started_at DESC)
                            FILTER (WHERE title IS NOT NULL))[1] AS title,
                        (ARRAY_AGG(thumbnail_url ORDER BY playback_started_at DESC)
                            FILTER (WHERE thumbnail_url IS NOT NULL))[1] AS thumbnail_url,
                        (ARRAY_AGG(creator_id ORDER BY playback_started_at DESC)
                            FILTER (WHERE creator_id IS NOT NULL))[1] AS creator_id,
                        (ARRAY_AGG(creator_name ORDER BY playback_started_at DESC)
                            FILTER (WHERE creator_name IS NOT NULL))[1] AS creator_name,
                        COUNT(*)::integer AS play_count,
                        COUNT(DISTINCT channel_id)::integer AS channel_count,
                        MAX(playback_started_at) AS last_played_at
                    FROM qualified
                    GROUP BY video_type, video_id
                ), ranked AS (
                    SELECT
                        ROW_NUMBER() OVER (
                            ORDER BY
                                CASE WHEN $4::text = 'global' THEN channel_count END DESC NULLS LAST,
                                play_count DESC,
                                last_played_at DESC,
                                video_type,
                                video_id
                        )::integer AS rank,
                        *
                    FROM aggregated
                )
                SELECT
                    ranked.*,
                    (
                        SELECT active.status
                        FROM video_queue AS active
                        WHERE active.channel_id = $1
                          AND active.video_type = ranked.video_type
                          AND active.video_id = ranked.video_id
                          AND active.status IN ('playing', 'queued')
                        ORDER BY CASE active.status WHEN 'playing' THEN 0 ELSE 1 END
                        LIMIT 1
                    ) AS active_status,
                    (
                        SELECT block.kind
                        FROM video_queue_blocklist AS block
                        WHERE block.channel_id = $1
                          AND block.kind IN ('video', 'creator', 'keyword')
                          AND (
                              block.kind = 'keyword'
                              OR block.video_type IS NULL
                              OR block.video_type = ranked.video_type
                          )
                          AND (
                              (block.kind = 'video' AND lower(block.value) = lower(ranked.video_id))
                              OR (
                                  block.kind = 'creator'
                                  AND ranked.creator_id IS NOT NULL
                                  AND lower(block.value) = lower(ranked.creator_id)
                              )
                              OR (
                                  block.kind = 'keyword'
                                  AND ranked.title IS NOT NULL
                                  AND STRPOS(lower(ranked.title), lower(block.value)) > 0
                              )
                          )
                        ORDER BY CASE block.kind WHEN 'video' THEN 0 WHEN 'creator' THEN 1 ELSE 2 END
                        LIMIT 1
                    ) AS blocked_kind
                FROM ranked
                ORDER BY rank
                LIMIT $5
                """,
                channel_id,
                days,
                video_type,
                scope,
                limit,
            )
        return [VideoQueueRankingEntry(**dict(row)) for row in rows]

    async def played_within(
        self,
        channel_id: str,
        video_id: str,
        hours: int,
        video_type: str = "youtube",
    ) -> bool:
        """True if this video actually started within the replay window."""
        async with self.pool.acquire() as conn:
            found = await conn.fetchval(
                "SELECT 1 FROM video_queue "
                "WHERE channel_id = $1 AND video_id = $2 AND video_type = $4 "
                "AND playback_started_at IS NOT NULL "
                "AND playback_started_at > NOW() - make_interval(hours => $3) "
                "LIMIT 1",
                channel_id,
                video_id,
                hours,
                video_type,
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
# VideoQueueInsertRepository
# ---------------------------------------------------------------------------


class VideoQueueInsertRepository:
    """Live insert (直播播放) state — one active insert per channel (migration 155)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_active(self, channel_id: str) -> VideoQueueInsert | None:
        async with self.pool.acquire() as conn:
            return await _fetch_active_insert(conn, channel_id)

    async def start(
        self,
        channel_id: str,
        *,
        source_type: str,
        source_id: str,
        title: str | None,
        creator_id: str | None,
        creator_name: str | None,
        thumbnail_url: str | None,
        volume_percent: int,
        audio_only: bool,
    ) -> VideoQueueInsert:
        """Start (or replace) the channel's insert.

        The insert is a background source: the queue keeps playing and has
        priority, and the overlay shows the insert only while nothing is
        queued. A video playing right now is left alone.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # A fresh row (new id) per start: the overlay ends inserts by
                # id, so a late report for the old one cannot stop this one.
                await conn.execute(
                    "DELETE FROM video_queue_inserts WHERE channel_id = $1", channel_id
                )
                row = await conn.fetchrow(
                    "INSERT INTO video_queue_inserts "
                    "(channel_id, source_type, source_id, title, creator_id, creator_name, "
                    " thumbnail_url, volume_percent, audio_only) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
                    f"RETURNING {_INSERT_COLUMNS}",
                    channel_id,
                    source_type,
                    source_id,
                    title,
                    creator_id,
                    creator_name,
                    thumbnail_url,
                    volume_percent,
                    audio_only,
                )
        return VideoQueueInsert(**dict(row))

    async def stop(self, channel_id: str, *, expected_id: int | None = None) -> bool:
        """End the channel's insert; with ``expected_id`` only that exact insert.

        Expired rows (past INSERT_MAX_HOURS) are removed too but report False:
        nothing was actually playing.

        The queue never waits on an insert, but a channel can still hold
        queued entries with nothing playing (e.g. rows left from before
        inserts stopped pausing the queue), so the next one is promoted here
        too rather than waiting for an overlay kickstart.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "DELETE FROM video_queue_inserts "
                    "WHERE channel_id = $1 AND ($2::bigint IS NULL OR id = $2) "
                    "RETURNING started_at > NOW() - make_interval(hours => $3) AS was_active",
                    channel_id,
                    expected_id,
                    INSERT_MAX_HOURS,
                )
                if row is not None:
                    await conn.execute(
                        "UPDATE video_queue "
                        "SET status = 'playing', started_at = NOW() "
                        "WHERE id = ("
                        "    SELECT id FROM video_queue "
                        "    WHERE channel_id = $1 AND status = 'queued' "
                        "    AND NOT EXISTS ("
                        "        SELECT 1 FROM video_queue "
                        "        WHERE channel_id = $1 AND status = 'playing'"
                        "    ) "
                        "    ORDER BY priority DESC, created_at ASC LIMIT 1"
                        ")",
                        channel_id,
                    )
        return bool(row and row["was_active"])

    async def update_playback(
        self, channel_id: str, *, volume_percent: int | None, audio_only: bool | None
    ) -> None:
        """Apply changed insert defaults to the insert that is playing now, if any."""
        if volume_percent is None and audio_only is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE video_queue_inserts SET "
                "volume_percent = COALESCE($2, volume_percent), "
                "audio_only = COALESCE($3, audio_only) "
                "WHERE channel_id = $1",
                channel_id,
                volume_percent,
                audio_only,
            )


async def _fetch_active_insert(
    conn: asyncpg.Connection, channel_id: str
) -> VideoQueueInsert | None:
    row = await conn.fetchrow(
        f"SELECT {_INSERT_COLUMNS} FROM video_queue_inserts "
        "WHERE channel_id = $1 AND started_at > NOW() - make_interval(hours => $2)",
        channel_id,
        INSERT_MAX_HOURS,
    )
    return VideoQueueInsert(**dict(row)) if row else None


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
        volume_percent: int | None = None,
        insert_audio_only: bool | None = None,
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
                    replay_cooldown_hours    = COALESCE($10, video_queue_settings.replay_cooldown_hours),
                    volume_percent           = COALESCE($11, video_queue_settings.volume_percent),
                    insert_audio_only        = COALESCE($12, video_queue_settings.insert_audio_only)
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
                volume_percent,
                insert_audio_only,
            )
            result = VideoQueueSettings(**dict(row))
            _settings_cache.invalidate(f"vq_settings:{channel_id}")
            return result

    async def overlay_key_matches(self, channel_id: str, overlay_key: UUID) -> bool:
        """Return whether the capability belongs to this channel."""
        async with self.pool.acquire() as conn:
            matched = await conn.fetchval(
                "SELECT EXISTS ("
                "SELECT 1 FROM video_queue_settings "
                "WHERE channel_id = $1 AND overlay_key = $2"
                ")",
                channel_id,
                overlay_key,
            )
        return bool(matched)

    async def rotate_overlay_key(self, channel_id: str) -> VideoQueueSettings:
        """Rotate the channel's overlay capability, invalidating old URLs."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO video_queue_settings (channel_id) VALUES ($1) "
                    "ON CONFLICT (channel_id) DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"""
                    UPDATE video_queue_settings
                    SET overlay_key = gen_random_uuid()
                    WHERE channel_id = $1
                    RETURNING {_SETTINGS_COLUMNS}
                    """,
                    channel_id,
                )
        if row is None:
            raise ValueError(f"Failed to rotate video queue overlay key for channel {channel_id}")
        _settings_cache.invalidate(f"vq_settings:{channel_id}")
        return VideoQueueSettings(**dict(row))


# ---------------------------------------------------------------------------
# VideoQueueBlocklistRepository
# ---------------------------------------------------------------------------


def _blocklist_match(
    entries: list[VideoQueueBlocklistEntry],
    *,
    video_type: str = "youtube",
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
        if (
            entry.kind in {"video", "creator"}
            and entry.video_type is not None
            and entry.video_type != video_type
        ):
            continue
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
        video_type: str | None = None,
        label: str | None = None,
        created_by: str | None = None,
    ) -> VideoQueueBlocklistEntry:
        """Insert a rule, or return its provider-scoped equivalent."""
        if kind not in BLOCKLIST_KINDS:
            raise ValueError(f"Unsupported blocklist kind: {kind}")
        if video_type is not None and kind not in {"video", "creator"}:
            raise ValueError("Only video and creator rules may specify a provider")
        if video_type is not None and video_type not in VIDEO_TYPES:
            raise ValueError(f"Unsupported video type: {video_type}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO video_queue_blocklist
                    (channel_id, kind, value, video_type, label, created_by)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (
                    channel_id, kind, lower(value), (COALESCE(video_type, '*'))
                ) DO UPDATE SET
                    label = COALESCE(EXCLUDED.label, video_queue_blocklist.label)
                RETURNING {_BLOCKLIST_COLUMNS}
                """,
                channel_id,
                kind,
                value,
                video_type,
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
        video_type: str = "youtube",
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
            video_type=video_type,
            video_id=video_id,
            title=title,
            requested_by=requested_by,
            requested_by_id=requested_by_id,
            creator_id=creator_id,
        )
