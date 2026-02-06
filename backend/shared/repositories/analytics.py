"""Repository for stream_sessions, command_stats, and stream_events tables."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import asyncpg

from shared.cache import _MISSING, AsyncTTLCache

logger = logging.getLogger(__name__)

# --- In-process caches ---
_session_cache = AsyncTTLCache(maxsize=32, ttl=10)
_summary_cache = AsyncTTLCache(maxsize=32, ttl=120)
_top_commands_cache = AsyncTTLCache(maxsize=32, ttl=120)


class AnalyticsRepository:
    """Pure SQL operations for stream analytics tables.

    Combines write operations (formerly ``AnalyticsDB``) and read
    operations (formerly ``AnalyticsService``) into a single repository.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ==================== Session Operations ====================

    async def create_session(
        self,
        channel_id: str,
        started_at: datetime,
        title: str | None = None,
        game_name: str | None = None,
    ) -> int:
        """Create a new stream session. Returns the session ID."""
        async with self.pool.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO stream_sessions (channel_id, started_at, title, game_name)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                channel_id,
                started_at,
                title,
                game_name,
            )
            if session_id is None:
                raise ValueError("Failed to create session: no ID returned")

            _session_cache.invalidate(f"active:{channel_id}")
            return int(session_id)

    async def get_active_session(self, channel_id: str) -> dict | None:
        """Get the currently active (un-ended) session for a channel."""
        cache_key = f"active:{channel_id}"
        cached = _session_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

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
            result = dict(row) if row else None
            _session_cache.set(cache_key, result)
            return result

    async def end_session(self, session_id: int, ended_at: datetime) -> None:
        """Mark a session as ended."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE stream_sessions SET ended_at = $1 WHERE id = $2",
                ended_at,
                session_id,
            )
        _session_cache.clear()

    # ==================== Event Recording ====================

    async def record_command_usage(
        self, session_id: int, channel_id: str, command_name: str
    ) -> None:
        """Increment (or create) a command usage counter for a session."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO command_stats (session_id, channel_id, command_name, usage_count, last_used_at)
                VALUES ($1, $2, $3, 1, NOW())
                ON CONFLICT (session_id, command_name)
                DO UPDATE SET
                    usage_count  = command_stats.usage_count + 1,
                    last_used_at = NOW()
                """,
                session_id,
                channel_id,
                command_name,
            )

    async def record_follow_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        occurred_at: datetime,
    ) -> None:
        """Record a follow event."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, display_name, occurred_at)
                VALUES ($1, $2, 'follow', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                display_name,
                occurred_at,
            )

    async def record_subscribe_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        tier: str,
        is_gift: bool,
        occurred_at: datetime,
    ) -> None:
        """Record a subscribe event."""
        metadata = {"tier": tier, "is_gift": is_gift}
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
                VALUES ($1, $2, 'subscribe', $3, $4, $5, $6, $7)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                display_name,
                metadata,
                occurred_at,
            )

    async def record_raid_event(
        self,
        session_id: int,
        channel_id: str,
        from_broadcaster_id: str,
        from_broadcaster_name: str,
        viewers: int,
        occurred_at: datetime,
    ) -> None:
        """Record a raid event."""
        metadata = {
            "viewers": viewers,
            "from_broadcaster_id": from_broadcaster_id,
            "from_broadcaster_name": from_broadcaster_name,
        }
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, metadata, occurred_at)
                VALUES ($1, $2, 'raid', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                from_broadcaster_id,
                from_broadcaster_name,
                metadata,
                occurred_at,
            )

    # ==================== Read / Aggregation Queries ====================

    async def get_summary(self, channel_id: str, days: int = 30) -> dict:
        """Get analytics summary for a channel over the given time window."""
        cache_key = f"summary:{channel_id}:{days}"
        cached = _summary_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

        async with self.pool.acquire() as conn:
            since_date = datetime.now() - timedelta(days=days)

            rows = await conn.fetch(
                """
                SELECT
                    s.id AS session_id,
                    s.channel_id,
                    s.started_at,
                    s.ended_at,
                    s.title,
                    s.game_name,
                    s.game_id,
                    EXTRACT(EPOCH FROM (COALESCE(s.ended_at, NOW()) - s.started_at)) / 3600 AS duration_hours,
                    COALESCE(SUM(c.usage_count), 0) AS total_commands,
                    COALESCE(SUM(CASE WHEN e.event_type = 'follow'    THEN 1 END), 0) AS new_follows,
                    COALESCE(SUM(CASE WHEN e.event_type = 'subscribe' THEN 1 END), 0) AS new_subs,
                    COALESCE(SUM(CASE WHEN e.event_type = 'raid'      THEN 1 END), 0) AS raids_received
                FROM stream_sessions s
                LEFT JOIN command_stats c ON c.session_id = s.id
                LEFT JOIN stream_events e ON e.session_id = s.id
                WHERE s.channel_id = $1 AND s.started_at >= $2
                GROUP BY s.id
                ORDER BY s.started_at DESC
                """,
                channel_id,
                since_date,
            )

            sessions = [
                {
                    "session_id": row["session_id"],
                    "channel_id": row["channel_id"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "title": row["title"],
                    "game_name": row["game_name"],
                    "game_id": row["game_id"],
                    "duration_hours": float(row["duration_hours"] or 0),
                    "total_commands": row["total_commands"] or 0,
                    "new_follows": row["new_follows"] or 0,
                    "new_subs": row["new_subs"] or 0,
                    "raids_received": row["raids_received"] or 0,
                }
                for row in rows
            ]

            total_sessions = len(sessions)
            total_stream_hours = sum(s["duration_hours"] for s in sessions)
            total_commands = sum(s["total_commands"] for s in sessions)
            total_follows = sum(s["new_follows"] for s in sessions)
            total_subs = sum(s["new_subs"] for s in sessions)
            avg_duration = total_stream_hours / total_sessions if total_sessions > 0 else 0

            result = {
                "total_sessions": total_sessions,
                "total_stream_hours": round(total_stream_hours, 2),
                "total_commands": total_commands,
                "total_follows": total_follows,
                "total_subs": total_subs,
                "avg_session_duration": round(avg_duration, 2),
                "recent_sessions": sessions[:25],
            }

            _summary_cache.set(cache_key, result)
            return result

    async def get_session_commands(self, session_id: int, channel_id: str) -> list[dict] | None:
        """Get command stats for a specific session (with ownership check)."""
        async with self.pool.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT channel_id FROM stream_sessions WHERE id = $1",
                session_id,
            )
            if not session or session["channel_id"] != channel_id:
                return None

            rows = await conn.fetch(
                """
                SELECT command_name, usage_count, last_used_at
                FROM command_stats
                WHERE session_id = $1
                ORDER BY usage_count DESC
                LIMIT 20
                """,
                session_id,
            )
            return [
                {
                    "command_name": row["command_name"],
                    "usage_count": row["usage_count"],
                    "last_used_at": row["last_used_at"],
                }
                for row in rows
            ]

    async def get_session_events(self, session_id: int, channel_id: str) -> list[dict] | None:
        """Get events for a specific session (with ownership check)."""
        async with self.pool.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT channel_id FROM stream_sessions WHERE id = $1",
                session_id,
            )
            if not session or session["channel_id"] != channel_id:
                return None

            rows = await conn.fetch(
                """
                SELECT event_type, user_id, username, display_name, metadata, occurred_at
                FROM stream_events
                WHERE session_id = $1
                ORDER BY occurred_at ASC
                """,
                session_id,
            )
            return [
                {
                    "event_type": row["event_type"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "metadata": row["metadata"],
                    "occurred_at": row["occurred_at"],
                }
                for row in rows
            ]

    async def list_top_commands(
        self, channel_id: str, days: int = 30, limit: int = 10
    ) -> list[dict]:
        """Get top commands across all sessions in the given time window."""
        cache_key = f"top_cmds:{channel_id}:{days}:{limit}"
        cached = _top_commands_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

        async with self.pool.acquire() as conn:
            since_date = datetime.now() - timedelta(days=days)

            rows = await conn.fetch(
                """
                SELECT
                    c.command_name,
                    SUM(c.usage_count) AS total_usage,
                    MAX(c.last_used_at) AS last_used
                FROM command_stats c
                JOIN stream_sessions s ON s.id = c.session_id
                WHERE c.channel_id = $1 AND s.started_at >= $2
                GROUP BY c.command_name
                ORDER BY total_usage DESC
                LIMIT $3
                """,
                channel_id,
                since_date,
                limit,
            )
            result = [
                {
                    "command_name": row["command_name"],
                    "usage_count": row["total_usage"],
                    "last_used_at": row["last_used"],
                }
                for row in rows
            ]

            _top_commands_cache.set(cache_key, result)
            return result

    # ==================== VOD Sync ====================

    async def sync_session_from_vod(
        self,
        channel_id: str,
        started_at: datetime,
        ended_at: datetime,
        title: str | None = None,
        game_name: str | None = None,
        game_id: str | None = None,
    ) -> int | None:
        """
        Create a session from VOD data if it doesn't already exist.

        Returns:
            Session ID if created, None if already exists.
        """
        async with self.pool.acquire() as conn:
            # Check for existing session with same start time
            existing = await conn.fetchrow(
                """
                SELECT id FROM stream_sessions
                WHERE channel_id = $1 AND started_at = $2
                """,
                channel_id,
                started_at,
            )
            if existing:
                return None

            # Create new session
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
