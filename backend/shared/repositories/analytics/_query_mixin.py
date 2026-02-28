"""Aggregation read queries for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg

from shared.cache import cached
from shared.repositories.analytics._caches import (
    _summary_cache,
    _top_chatters_cache,
    _top_commands_cache,
)


class _AnalyticsQueryMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

    # ==================== Per-session detail ====================

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

    # ==================== Channel-level aggregations ====================

    @cached(
        cache=_summary_cache,
        key_func=lambda self, channel_id, days=30: f"summary:{channel_id}:{days}",
    )
    async def get_summary(self, channel_id: str, days: int = 30) -> dict:
        """Get analytics summary for a channel over the given time window."""
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)

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
                    EXTRACT(EPOCH FROM (COALESCE(s.ended_at, NOW()) - s.started_at)) / 3600
                        AS duration_hours,
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

            return {
                "total_sessions": total_sessions,
                "total_stream_hours": round(total_stream_hours, 2),
                "total_commands": total_commands,
                "total_follows": total_follows,
                "total_subs": total_subs,
                "avg_session_duration": round(avg_duration, 2),
                "recent_sessions": sessions[:25],
            }

    @cached(
        cache=_top_commands_cache,
        key_func=lambda self, channel_id, days=30, limit=10: (
            f"top_cmds:{channel_id}:{days}:{limit}"
        ),
    )
    async def list_top_commands(
        self, channel_id: str, days: int = 30, limit: int = 10
    ) -> list[dict]:
        """Get top commands across all sessions in the given time window."""
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)

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
            return [
                {
                    "command_name": row["command_name"],
                    "usage_count": row["total_usage"],
                    "last_used_at": row["last_used"],
                }
                for row in rows
            ]

    @cached(
        cache=_top_chatters_cache,
        key_func=lambda self, channel_id, days=30, limit=10: (
            f"top_chatters:{channel_id}:{days}:{limit}"
        ),
    )
    async def list_top_chatters(
        self, channel_id: str, days: int = 30, limit: int = 10
    ) -> list[dict]:
        """Get top chatters across all sessions in the given time window."""
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)

            rows = await conn.fetch(
                """
                SELECT
                    c.user_id,
                    (ARRAY_AGG(c.username ORDER BY c.last_message_at DESC))[1] AS username,
                    SUM(c.message_count) AS total_messages
                FROM chatter_stats c
                JOIN stream_sessions s ON s.id = c.session_id
                WHERE c.channel_id = $1 AND s.started_at >= $2
                GROUP BY c.user_id
                ORDER BY total_messages DESC
                LIMIT $3
                """,
                channel_id,
                since_date,
                limit,
            )
            return [
                {
                    "username": row["username"],
                    "message_count": row["total_messages"],
                }
                for row in rows
            ]

    async def list_top_commands_from_config(
        self, channel_id: str, days: int = 30, limit: int = 10
    ) -> list[dict]:
        """Get top commands directly from command_configs.usage_count.

        Session-independent — always has data regardless of stream state.
        Filters to commands used within the given time window via last_used_at.
        """
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)
            rows = await conn.fetch(
                """
                SELECT command_name, usage_count
                FROM command_configs
                WHERE channel_id = $1
                  AND enabled = TRUE
                  AND usage_count > 0
                  AND last_used_at >= $2
                ORDER BY usage_count DESC
                LIMIT $3
                """,
                channel_id,
                since_date,
                limit,
            )
            return [
                {
                    "command_name": f"!{row['command_name']}",
                    "usage_count": row["usage_count"],
                }
                for row in rows
            ]

    async def get_total_commands_from_config(self, channel_id: str) -> int:
        """Get all-time total command usage from command_configs (session-independent)."""
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COALESCE(SUM(usage_count), 0) FROM command_configs WHERE channel_id = $1",
                channel_id,
            )
            return int(total)

    async def get_total_messages(self, channel_id: str, days: int = 30) -> int:
        """Get total message count across all sessions in the given time window."""
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)

            total = await conn.fetchval(
                """
                SELECT COALESCE(SUM(c.message_count), 0)
                FROM chatter_stats c
                JOIN stream_sessions s ON s.id = c.session_id
                WHERE c.channel_id = $1 AND s.started_at >= $2
                """,
                channel_id,
                since_date,
            )
            return int(total)
