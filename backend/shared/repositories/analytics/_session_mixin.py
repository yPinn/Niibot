"""Session lifecycle and VOD-sync operations for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from shared.cache import cached
from shared.repositories.analytics._caches import _session_cache, _summary_cache


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

    async def end_session(self, session_id: int, ended_at: datetime) -> None:
        """Mark a session as ended."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE stream_sessions SET ended_at = $1 WHERE id = $2",
                ended_at,
                session_id,
            )
        _session_cache.clear()

    async def close_stale_sessions(self, max_hours: int = 12) -> int:
        """Close sessions running longer than max_hours without ended_at.

        Returns the number of sessions closed.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE stream_sessions
                SET ended_at = started_at + INTERVAL '1 hour' * $1
                WHERE ended_at IS NULL
                  AND started_at < NOW() - INTERVAL '1 hour' * $1
                """,
                float(max_hours),
            )
        _session_cache.clear()
        count = int(result.split()[-1]) if result else 0
        return count

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
                "SELECT id FROM stream_sessions WHERE channel_id = $1 AND started_at = $2",
                channel_id,
                started_at,
            )
            if existing:
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
