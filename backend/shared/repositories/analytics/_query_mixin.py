"""Aggregation read queries for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import asyncio
import json
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
                WITH recent AS (
                    SELECT DISTINCT ON (c.user_id)
                        c.user_id,
                        c.username,
                        c.display_name
                    FROM chatter_stats c
                    JOIN stream_sessions s ON s.id = c.session_id
                    WHERE c.channel_id = $1 AND s.started_at >= $2
                    ORDER BY c.user_id, c.last_message_at DESC
                ),
                totals AS (
                    SELECT c.user_id, SUM(c.message_count) AS total_messages
                    FROM chatter_stats c
                    JOIN stream_sessions s ON s.id = c.session_id
                    WHERE c.channel_id = $1 AND s.started_at >= $2
                    GROUP BY c.user_id
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
                """,
                channel_id,
                since_date,
            )
            return int(total)

    async def get_insights(self, channel_id: str, days: int = 30) -> dict:
        """Aggregate channel insights for the Insights page.

        Returns event totals, message/command counts, top chatters, and top commands.
        Three queries run in parallel via separate pool connections.
        """
        since_date = datetime.now(UTC) - timedelta(days=days)

        async def _summary() -> dict:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    WITH session_scope AS (
                        SELECT id FROM stream_sessions
                        WHERE channel_id = $1 AND started_at >= $2
                    ),
                    msg_totals AS (
                        SELECT COALESCE(SUM(c.message_count), 0) AS total_messages
                        FROM chatter_stats c
                        WHERE c.channel_id = $1
                          AND c.session_id IN (SELECT id FROM session_scope)
                    ),
                    cmd_totals AS (
                        SELECT COALESCE(SUM(c.usage_count), 0) AS total_commands
                        FROM command_stats c
                        WHERE c.channel_id = $1
                          AND c.session_id IN (SELECT id FROM session_scope)
                    ),
                    event_totals AS (
                        SELECT
                            COALESCE(SUM(CASE WHEN event_type = 'follow'    THEN 1 END), 0) AS total_follows,
                            COALESCE(SUM(CASE WHEN event_type = 'subscribe' THEN 1 END), 0) AS total_subs,
                            COALESCE(SUM(CASE WHEN event_type = 'raid'      THEN 1 END), 0) AS total_raids,
                            COALESCE(SUM(CASE WHEN event_type = 'cheer'     THEN 1 END), 0) AS total_cheers,
                            COALESCE(SUM(
                                CASE WHEN event_type = 'cheer'
                                THEN COALESCE((metadata->>'bits')::int, 0) END
                            ), 0) AS total_bits
                        FROM stream_events
                        WHERE channel_id = $1
                          AND session_id IN (SELECT id FROM session_scope)
                    )
                    SELECT
                        m.total_messages,
                        c.total_commands,
                        e.total_follows,
                        e.total_subs,
                        e.total_raids,
                        e.total_cheers,
                        e.total_bits
                    FROM msg_totals m, cmd_totals c, event_totals e
                    """,
                    channel_id,
                    since_date,
                )
                return {
                    "total_messages": int(row["total_messages"]),
                    "total_commands": int(row["total_commands"]),
                    "total_follows": int(row["total_follows"]),
                    "total_subs": int(row["total_subs"]),
                    "total_raids": int(row["total_raids"]),
                    "total_cheers": int(row["total_cheers"]),
                    "total_bits": int(row["total_bits"]),
                }

        async def _top_chatters() -> list[dict]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    WITH totals AS (
                        SELECT c.user_id, SUM(c.message_count) AS total
                        FROM chatter_stats c
                        JOIN stream_sessions s ON s.id = c.session_id
                        WHERE c.channel_id = $1 AND s.started_at >= $2
                        GROUP BY c.user_id
                    ),
                    latest_name AS (
                        SELECT DISTINCT ON (c.user_id) c.user_id, c.username, c.display_name
                        FROM chatter_stats c
                        JOIN stream_sessions s ON s.id = c.session_id
                        WHERE c.channel_id = $1 AND s.started_at >= $2
                        ORDER BY c.user_id, c.last_message_at DESC
                    )
                    SELECT n.username, n.display_name, t.total AS message_count
                    FROM totals t
                    JOIN latest_name n ON n.user_id = t.user_id
                    ORDER BY t.total DESC
                    LIMIT 10
                    """,
                    channel_id,
                    since_date,
                )
                return [
                    {
                        "username": r["username"],
                        "display_name": r["display_name"],
                        "message_count": int(r["message_count"]),
                    }
                    for r in rows
                ]

        async def _top_commands() -> list[dict]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT c.command_name, SUM(c.usage_count) AS usage_count
                    FROM command_stats c
                    JOIN stream_sessions s ON s.id = c.session_id
                    WHERE c.channel_id = $1 AND s.started_at >= $2
                    GROUP BY c.command_name
                    ORDER BY usage_count DESC
                    LIMIT 10
                    """,
                    channel_id,
                    since_date,
                )
                return [
                    {"command_name": r["command_name"], "usage_count": int(r["usage_count"])}
                    for r in rows
                ]

        summary, top_chatters, top_commands = await asyncio.gather(
            _summary(), _top_chatters(), _top_commands()
        )
        return {**summary, "top_chatters": top_chatters, "top_commands": top_commands}

    async def list_viewers(self, channel_id: str, days: int = 30, limit: int = 50) -> list[dict]:
        """Top chatters with enriched stats for the Insights viewers list."""
        since_date = datetime.now(UTC) - timedelta(days=days)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH session_scope AS (
                    SELECT id FROM stream_sessions
                    WHERE channel_id = $1 AND started_at >= $2
                ),
                chatter_totals AS (
                    SELECT
                        c.user_id,
                        SUM(c.message_count)        AS total_messages,
                        COUNT(DISTINCT c.session_id) AS sessions_attended,
                        MAX(c.last_message_at)       AS last_seen
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                    GROUP BY c.user_id
                ),
                latest_name AS (
                    SELECT DISTINCT ON (c.user_id)
                        c.user_id, c.username, c.display_name
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                    ORDER BY c.user_id, c.last_message_at DESC
                ),
                cheer_totals AS (
                    SELECT user_id, SUM((metadata->>'bits')::int) AS total_bits
                    FROM stream_events
                    WHERE channel_id = $1
                      AND event_type = 'cheer'
                      AND user_id IS NOT NULL
                      AND session_id IN (SELECT id FROM session_scope)
                    GROUP BY user_id
                )
                SELECT
                    n.user_id,
                    n.username,
                    n.display_name,
                    t.total_messages,
                    t.sessions_attended,
                    t.last_seen,
                    COALESCE(ch.total_bits, 0) AS total_bits
                FROM chatter_totals t
                JOIN latest_name n ON n.user_id = t.user_id
                LEFT JOIN cheer_totals ch ON ch.user_id = t.user_id
                ORDER BY t.total_messages DESC
                LIMIT $3
                """,
                channel_id,
                since_date,
                limit,
            )
            return [
                {
                    "user_id": r["user_id"],
                    "username": r["username"],
                    "display_name": r["display_name"],
                    "total_messages": int(r["total_messages"]),
                    "sessions_attended": int(r["sessions_attended"]),
                    "last_seen": r["last_seen"],
                    "total_bits": int(r["total_bits"]),
                }
                for r in rows
            ]

    async def get_viewer_profile(
        self, channel_id: str, user_id: str, days: int = 30
    ) -> dict | None:
        """Detailed viewer profile combining chatter_stats and stream_events."""
        since_date = datetime.now(UTC) - timedelta(days=days)

        async def _stats() -> dict | None:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    WITH session_scope AS (
                        SELECT id FROM stream_sessions
                        WHERE channel_id = $1 AND started_at >= $2
                    ),
                    rows AS (
                        SELECT
                            c.username,
                            c.display_name,
                            c.message_count,
                            c.session_id,
                            c.last_message_at,
                            ROW_NUMBER() OVER (ORDER BY c.last_message_at DESC) AS rn
                        FROM chatter_stats c
                        WHERE c.channel_id = $1 AND c.user_id = $3
                          AND c.session_id IN (SELECT id FROM session_scope)
                    )
                    SELECT
                        MAX(CASE WHEN rn = 1 THEN username     END) AS username,
                        MAX(CASE WHEN rn = 1 THEN display_name END) AS display_name,
                        COALESCE(SUM(message_count), 0)             AS total_messages,
                        COUNT(DISTINCT session_id)                   AS sessions_attended,
                        MAX(last_message_at)                        AS last_seen
                    FROM rows
                    """,
                    channel_id,
                    since_date,
                    user_id,
                )
                if not row or row["username"] is None:
                    return None
                return {
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "total_messages": int(row["total_messages"]),
                    "sessions_attended": int(row["sessions_attended"]),
                    "last_seen": row["last_seen"],
                }

        async def _events() -> list[dict]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT event_type, metadata, occurred_at
                    FROM stream_events
                    WHERE channel_id = $1 AND user_id = $3
                      AND session_id IN (
                          SELECT id FROM stream_sessions
                          WHERE channel_id = $1 AND started_at >= $2
                      )
                    ORDER BY occurred_at DESC
                    LIMIT 50
                    """,
                    channel_id,
                    since_date,
                    user_id,
                )
                return [
                    {
                        "event_type": r["event_type"],
                        "metadata": r["metadata"],
                        "occurred_at": r["occurred_at"],
                    }
                    for r in rows
                ]

        async def _follow_since() -> datetime | None:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT occurred_at FROM stream_events
                    WHERE channel_id = $1 AND user_id = $2 AND event_type = 'follow'
                    ORDER BY occurred_at ASC
                    LIMIT 1
                    """,
                    channel_id,
                    user_id,
                )
                return row["occurred_at"] if row else None

        stats, events, follow_since = await asyncio.gather(_stats(), _events(), _follow_since())
        if stats is None:
            return None

        total_bits = sum(
            int((e["metadata"] or {}).get("bits", 0)) for e in events if e["event_type"] == "cheer"
        )

        return {
            "user_id": user_id,
            **stats,
            "total_bits": total_bits,
            "follow_since": follow_since,
            "events": events,
        }
