"""Channel-level aggregation queries for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import asyncpg

from shared.cache import cached
from shared.repositories.analytics._caches import (
    _summary_cache,
    _top_chatters_cache,
    _top_commands_cache,
)


class _SummaryQueryMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

    # ==================== Channel-level aggregations ====================

    @cached(
        cache=_summary_cache,
        key_func=lambda self, channel_id, days=30: f"summary:{channel_id}:{days}",
    )
    async def get_summary(self, channel_id: str, days: int = 30) -> dict:
        """Get analytics summary for a channel over the given time window."""
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)

            row = await conn.fetchrow(
                """
                WITH cmd_totals AS (
                    SELECT session_id, SUM(usage_count) AS total_commands
                    FROM command_stats
                    GROUP BY session_id
                ),
                event_counts AS (
                    SELECT
                        session_id,
                        SUM(CASE WHEN event_type = 'follow'    THEN 1 ELSE 0 END) AS new_follows,
                        SUM(CASE WHEN event_type = 'subscribe' THEN 1 ELSE 0 END) AS new_subs,
                        SUM(CASE WHEN event_type = 'raid'      THEN 1 ELSE 0 END) AS raids_received
                    FROM stream_events
                    GROUP BY session_id
                ),
                session_data AS (
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
                        COALESCE(c.total_commands, 0)  AS total_commands,
                        COALESCE(e.new_follows, 0)     AS new_follows,
                        COALESCE(e.new_subs, 0)        AS new_subs,
                        COALESCE(e.raids_received, 0)  AS raids_received
                    FROM stream_sessions s
                    LEFT JOIN cmd_totals   c ON c.session_id = s.id
                    LEFT JOIN event_counts e ON e.session_id = s.id
                    WHERE s.channel_id = $1 AND s.started_at >= $2
                ),
                aggregates AS (
                    SELECT
                        COUNT(*)                        AS total_sessions,
                        COALESCE(SUM(duration_hours),  0) AS total_stream_hours,
                        COALESCE(SUM(total_commands),  0) AS total_commands,
                        COALESCE(SUM(new_follows),     0) AS total_follows,
                        COALESCE(SUM(new_subs),        0) AS total_subs,
                        CASE WHEN COUNT(*) > 0
                            THEN SUM(duration_hours) / COUNT(*)
                            ELSE 0
                        END                             AS avg_session_duration
                    FROM session_data
                )
                SELECT
                    a.total_sessions,
                    a.total_stream_hours,
                    a.total_commands,
                    a.total_follows,
                    a.total_subs,
                    a.avg_session_duration,
                    COALESCE(
                        (SELECT json_agg(s ORDER BY s.started_at DESC)
                         FROM (SELECT * FROM session_data ORDER BY started_at DESC LIMIT 90) s),
                        '[]'::json
                    ) AS recent_sessions
                FROM aggregates a
                """,
                channel_id,
                since_date,
            )

            raw = row["recent_sessions"]
            sessions = json.loads(raw) if isinstance(raw, str) else (raw or [])

            return {
                "total_sessions": row["total_sessions"],
                "total_stream_hours": round(float(row["total_stream_hours"]), 2),
                "total_commands": row["total_commands"],
                "total_follows": row["total_follows"],
                "total_subs": row["total_subs"],
                "avg_session_duration": round(float(row["avg_session_duration"]), 2),
                "recent_sessions": sessions,
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
                WITH session_scope AS MATERIALIZED (
                    SELECT id FROM stream_sessions
                    WHERE channel_id = $1 AND started_at >= $2
                ),
                chatter_base AS MATERIALIZED (
                    SELECT c.user_id, c.username, c.display_name,
                           c.message_count, c.last_message_at
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                      AND c.user_id != $1
                ),
                recent AS (
                    SELECT DISTINCT ON (user_id) user_id, username, display_name
                    FROM chatter_base
                    ORDER BY user_id, last_message_at DESC
                ),
                totals AS (
                    SELECT user_id, SUM(message_count) AS total_messages
                    FROM chatter_base
                    GROUP BY user_id
                )
                SELECT r.user_id, r.username, r.display_name, t.total_messages
                FROM recent r
                JOIN totals t ON t.user_id = r.user_id
                ORDER BY t.total_messages DESC
                LIMIT $3
                """,
                channel_id,
                since_date,
                limit,
            )
            return [
                {
                    "username": row["username"],
                    "display_name": row["display_name"],
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

    async def get_total_commands_from_config(self, channel_id: str, days: int = 30) -> int:
        """Get total command usage from command_configs filtered to the given time window."""
        async with self.pool.acquire() as conn:
            since_date = datetime.now(UTC) - timedelta(days=days)
            total = await conn.fetchval(
                """
                SELECT COALESCE(SUM(usage_count), 0)
                FROM command_configs
                WHERE channel_id = $1
                  AND last_used_at >= $2
                """,
                channel_id,
                since_date,
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
                  AND c.user_id != $1
                """,
                channel_id,
                since_date,
            )
            return int(total)
