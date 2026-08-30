"""Session lifecycle and VOD-sync operations for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import logging
from datetime import datetime

import asyncpg

from shared.cache import cached
from shared.repositories.analytics._caches import _session_cache, _summary_cache

LOGGER: logging.Logger = logging.getLogger(__name__)


class _AnalyticsSessionMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

    # ==================== Session lifecycle ====================

    async def create_session(
        self,
        channel_id: str,
        started_at: datetime,
        title: str | None = None,
        game_name: str | None = None,
        game_id: str | None = None,
    ) -> int:
        """Create a new stream session. Returns the session ID."""
        async with self.pool.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO stream_sessions (channel_id, started_at, title, game_name, game_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                channel_id,
                started_at,
                title,
                game_name,
                game_id,
            )
            if session_id is None:
                raise ValueError("Failed to create session: no ID returned")

            _session_cache.invalidate(f"active:{channel_id}")
            return int(session_id)

    @cached(cache=_session_cache, key_func=lambda self, channel_id: f"active:{channel_id}")
    async def get_active_session(self, channel_id: str) -> dict | None:
        """Get the currently active (un-ended) session for a channel."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, channel_id, started_at, ended_at, title, game_name
                FROM stream_sessions
                WHERE channel_id = $1 AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                channel_id,
            )
            return dict(row) if row else None

    async def update_attendance_streaks(self, channel_id: str, session_id: int) -> None:
        """Update streaks using only sessions with a complete attendance snapshot.

        Increments streak_count if the viewer also attended the previous session,
        otherwise resets to 1. Tracks best_streak as the all-time high water mark.
        Viewers who attended the previous session but missed this one have their
        streak_count reset to 0. Unobserved sessions do not change the projection.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                WITH current_session AS (
                    SELECT id, started_at
                    FROM stream_sessions
                    WHERE channel_id = $1
                      AND id = $2
                      AND ended_at IS NOT NULL
                      AND attendance_snapshot_count > 0
                ),
                prev_session AS (
                    SELECT s.id
                    FROM stream_sessions s
                    CROSS JOIN current_session cur
                    WHERE s.channel_id = $1
                      AND s.ended_at IS NOT NULL
                      AND s.attendance_snapshot_count > 0
                      AND (s.started_at, s.id) < (cur.started_at, cur.id)
                    ORDER BY s.started_at DESC, s.id DESC
                    LIMIT 1
                ),
                current_attendees AS (
                    SELECT cs.user_id
                    FROM chatter_stats cs
                    JOIN current_session cur ON cur.id = cs.session_id
                    WHERE cs.channel_id = $1
                ),
                prev_attendees AS (
                    SELECT user_id FROM chatter_stats
                    WHERE channel_id = $1
                      AND session_id = (SELECT id FROM prev_session)
                ),
                existing_streaks AS (
                    SELECT user_id, streak_count, last_session_id
                    FROM viewer_attendance_streaks
                    WHERE channel_id = $1
                ),
                new_streaks AS (
                    SELECT
                        ca.user_id,
                        CASE WHEN es.last_session_id = $2
                            THEN es.streak_count
                            WHEN pa.user_id IS NOT NULL
                            THEN COALESCE(es.streak_count, 0) + 1
                            ELSE 1
                        END AS streak_count
                    FROM current_attendees ca
                    LEFT JOIN prev_attendees  pa ON pa.user_id = ca.user_id
                    LEFT JOIN existing_streaks es ON es.user_id = ca.user_id
                )
                INSERT INTO viewer_attendance_streaks
                    (channel_id, user_id, streak_count, best_streak, last_session_id, updated_at)
                SELECT $1, ns.user_id, ns.streak_count, ns.streak_count, $2, NOW()
                FROM new_streaks ns
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    streak_count    = EXCLUDED.streak_count,
                    best_streak     = GREATEST(viewer_attendance_streaks.best_streak,
                                               EXCLUDED.streak_count),
                    last_session_id = EXCLUDED.last_session_id,
                    updated_at      = EXCLUDED.updated_at
                """,
                channel_id,
                session_id,
            )
            # Reset streak for viewers who attended the previous session but missed this one
            await conn.execute(
                """
                WITH current_session AS (
                    SELECT id, started_at
                    FROM stream_sessions
                    WHERE channel_id = $1
                      AND id = $2
                      AND ended_at IS NOT NULL
                      AND attendance_snapshot_count > 0
                ),
                prev_session AS (
                    SELECT s.id
                    FROM stream_sessions s
                    CROSS JOIN current_session cur
                    WHERE s.channel_id = $1
                      AND s.ended_at IS NOT NULL
                      AND s.attendance_snapshot_count > 0
                      AND (s.started_at, s.id) < (cur.started_at, cur.id)
                    ORDER BY s.started_at DESC, s.id DESC
                    LIMIT 1
                )
                UPDATE viewer_attendance_streaks
                SET streak_count = 0, updated_at = NOW()
                WHERE channel_id = $1
                  AND last_session_id = (SELECT id FROM prev_session)
                  AND user_id NOT IN (
                      SELECT cs.user_id
                      FROM chatter_stats cs
                      JOIN current_session cur ON cur.id = cs.session_id
                      WHERE cs.channel_id = $1
                  )
                """,
                channel_id,
                session_id,
            )

    async def end_session(self, session_id: int, ended_at: datetime) -> None:
        """Mark a session as ended and update viewer attendance streaks."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE stream_sessions SET ended_at = $1 WHERE id = $2 RETURNING channel_id",
                ended_at,
                session_id,
            )
        _session_cache.clear()
        if row:
            try:
                await self.update_attendance_streaks(row["channel_id"], session_id)
            except Exception as e:
                LOGGER.warning(
                    "Failed to update attendance streaks for session %s: %s", session_id, e
                )

    async def close_stale_sessions(self, max_hours: int = 12) -> int:
        """Close sessions running longer than max_hours without ended_at.

        Returns the number of sessions closed.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE stream_sessions
                SET ended_at = started_at + INTERVAL '1 hour' * $1
                WHERE ended_at IS NULL
                  AND started_at < NOW() - INTERVAL '1 hour' * $1
                RETURNING id, channel_id, started_at, attendance_snapshot_count
                """,
                float(max_hours),
            )
        _session_cache.clear()
        ordered_rows = sorted(
            rows, key=lambda row: (row["channel_id"], row["started_at"], row["id"])
        )
        for row in ordered_rows:
            if row["attendance_snapshot_count"] <= 0:
                continue
            try:
                await self.update_attendance_streaks(row["channel_id"], row["id"])
            except Exception as e:
                LOGGER.warning(
                    "Failed to update attendance streaks for stale session %s: %s",
                    row["id"],
                    e,
                )
        return len(rows)

    # ==================== VOD reconciliation ====================

    async def reconcile_sessions_with_vods(
        self,
        channel_id: str,
        vods: list[dict],
    ) -> int:
        """Fix session ended_at using VOD data from Twitch API.

        Matches sessions by started_at (within 5 min tolerance).
        Updates ended_at if the VOD-derived value differs by >10 min.
        Returns the number of sessions updated.
        """
        if not vods:
            return 0

        updated = 0
        async with self.pool.acquire() as conn:
            for vod in vods:
                vod_start = vod["started_at"]
                vod_end = vod["ended_at"]

                row = await conn.fetchrow(
                    """
                    SELECT id, ended_at FROM stream_sessions
                    WHERE channel_id = $1
                      AND ABS(EXTRACT(EPOCH FROM (started_at - $2))) < 300
                    ORDER BY ABS(EXTRACT(EPOCH FROM (started_at - $2)))
                    LIMIT 1
                    """,
                    channel_id,
                    vod_start,
                )
                if not row:
                    continue

                current_end = row["ended_at"]
                needs_update = (
                    current_end is None or abs((current_end - vod_end).total_seconds()) > 600
                )
                if needs_update:
                    await conn.execute(
                        "UPDATE stream_sessions SET ended_at = $1 WHERE id = $2",
                        vod_end,
                        row["id"],
                    )
                    updated += 1

        if updated:
            _session_cache.clear()
            _summary_cache.clear()
        return updated

    async def sync_session_from_vod(
        self,
        channel_id: str,
        started_at: datetime,
        ended_at: datetime,
        title: str | None = None,
        game_name: str | None = None,
        game_id: str | None = None,
    ) -> int | None:
        """Create a session from VOD data if it doesn't already exist.

        Returns session ID if created, None if already exists.
        """
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, title FROM stream_sessions WHERE channel_id = $1 AND started_at = $2",
                channel_id,
                started_at,
            )
            if existing:
                if existing["title"] is None and title:
                    await conn.execute(
                        "UPDATE stream_sessions SET title = $1 WHERE id = $2",
                        title,
                        existing["id"],
                    )
                    _session_cache.clear()
                    _summary_cache.clear()
                return None

            session_id = await conn.fetchval(
                """
                INSERT INTO stream_sessions
                    (channel_id, started_at, ended_at, title, game_name, game_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                channel_id,
                started_at,
                ended_at,
                title,
                game_name,
                game_id,
            )
            return int(session_id) if session_id else None

    async def get_latest_session_time(self, channel_id: str) -> datetime | None:
        """Get the start time of the most recent session for a channel."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT started_at FROM stream_sessions
                WHERE channel_id = $1
                ORDER BY started_at DESC
                LIMIT 1
                """,
                channel_id,
            )
            return row["started_at"] if row else None
