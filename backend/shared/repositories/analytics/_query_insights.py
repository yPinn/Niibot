"""Insights-page aggregation query for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg

from shared.repositories.analytics import _query_common
from shared.repositories.analytics._query_common import (
    _SESSION_CHART_LIMIT,
    _TOP_CHATTERS_LIMIT,
    _TOP_COMMANDS_LIMIT,
    _TOP_GAMES_LIMIT,
)


class _InsightsQueryMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

    async def get_insights(self, channel_id: str, days: int = 30) -> dict:
        """Aggregate channel insights for the Insights page.

        Returns event totals, message/command counts, top chatters, and top commands.
        Six queries run in parallel via separate pool connections.
        """
        since_date = datetime.now(UTC) - timedelta(days=days)
        bots = await _query_common._get_bot_list()

        async def _summary() -> dict:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    WITH session_scope AS MATERIALIZED (
                        SELECT id,
                            EXTRACT(EPOCH FROM (COALESCE(ended_at, NOW()) - started_at)) AS duration_seconds
                        FROM stream_sessions
                        WHERE channel_id = $1 AND started_at >= $2
                    ),
                    session_stats AS (
                        SELECT
                            COUNT(*) AS total_sessions,
                            COALESCE(SUM(duration_seconds), 0) AS total_stream_seconds
                        FROM session_scope
                    ),
                    msg_totals AS (
                        SELECT COALESCE(SUM(c.message_count), 0) AS total_messages
                        FROM chatter_stats c
                        WHERE c.channel_id = $1
                          AND c.session_id IN (SELECT id FROM session_scope)
                          AND c.user_id != $1
                          AND lower(c.username) != ALL($3::text[])
                    ),
                    cmd_totals AS (
                        SELECT COALESCE(SUM(c.usage_count), 0) AS total_commands
                        FROM command_stats c
                        WHERE c.channel_id = $1
                          AND c.session_id IN (SELECT id FROM session_scope)
                    ),
                    event_totals AS (
                        SELECT
                            COALESCE(SUM(CASE WHEN event_type = 'follow' THEN 1 END), 0) AS total_follows,
                            COALESCE(SUM(CASE WHEN event_type = 'subscribe'
                                              AND NOT COALESCE((metadata->>'is_gift')::bool, false)
                                         THEN 1 END), 0) AS total_organic_subs,
                            COALESCE(SUM(CASE WHEN event_type = 'subscribe'
                                              AND COALESCE((metadata->>'is_gift')::bool, false)
                                         THEN 1 END), 0) AS total_gift_subs,
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
                        ss.total_sessions,
                        ss.total_stream_seconds,
                        m.total_messages,
                        c.total_commands,
                        e.total_follows,
                        e.total_organic_subs,
                        e.total_gift_subs,
                        e.total_raids,
                        e.total_cheers,
                        e.total_bits
                    FROM session_stats ss, msg_totals m, cmd_totals c, event_totals e
                    """,
                    channel_id,
                    since_date,
                    bots,
                )
                return {
                    "total_sessions": int(row["total_sessions"]),
                    "total_stream_seconds": int(row["total_stream_seconds"]),
                    "total_messages": int(row["total_messages"]),
                    "total_commands": int(row["total_commands"]),
                    "total_follows": int(row["total_follows"]),
                    "total_organic_subs": int(row["total_organic_subs"]),
                    "total_gift_subs": int(row["total_gift_subs"]),
                    "total_raids": int(row["total_raids"]),
                    "total_cheers": int(row["total_cheers"]),
                    "total_bits": int(row["total_bits"]),
                }

        async def _top_chatters() -> list[dict]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
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
                          AND lower(c.username) != ALL($3::text[])
                    ),
                    totals AS (
                        SELECT user_id, SUM(message_count) AS total
                        FROM chatter_base
                        GROUP BY user_id
                    ),
                    latest_name AS (
                        SELECT DISTINCT ON (user_id) user_id, username, display_name
                        FROM chatter_base
                        ORDER BY user_id, last_message_at DESC
                    )
                    SELECT n.username, n.display_name, t.total AS message_count
                    FROM totals t
                    JOIN latest_name n ON n.user_id = t.user_id
                    ORDER BY t.total DESC
                    LIMIT {_TOP_CHATTERS_LIMIT}
                    """,
                    channel_id,
                    since_date,
                    bots,
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
                    f"""
                    SELECT c.command_name, SUM(c.usage_count) AS usage_count
                    FROM command_stats c
                    JOIN stream_sessions s ON s.id = c.session_id
                    WHERE c.channel_id = $1 AND s.started_at >= $2
                    GROUP BY c.command_name
                    ORDER BY usage_count DESC
                    LIMIT {_TOP_COMMANDS_LIMIT}
                    """,
                    channel_id,
                    since_date,
                )
                return [
                    {"command_name": r["command_name"], "usage_count": int(r["usage_count"])}
                    for r in rows
                ]

        async def _session_chart() -> list[dict]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT s.started_at,
                           COALESCE(s.game_name, '') AS game_name,
                           COALESCE(SUM(c.watch_seconds), 0)::int AS total_watch_seconds
                    FROM stream_sessions s
                    LEFT JOIN chatter_stats c
                        ON c.session_id = s.id AND c.channel_id = $1
                        AND c.user_id != $1
                        AND lower(c.username) != ALL($3::text[])
                    WHERE s.channel_id = $1 AND s.started_at >= $2
                    GROUP BY s.id, s.started_at, s.game_name
                    ORDER BY s.started_at ASC
                    LIMIT {_SESSION_CHART_LIMIT}
                    """,
                    channel_id,
                    since_date,
                    bots,
                )
                return [
                    {
                        "started_at": r["started_at"].isoformat(),
                        "game_name": r["game_name"] or None,
                        "total_watch_hours": round(int(r["total_watch_seconds"]) / 3600, 2),
                    }
                    for r in rows
                ]

        async def _top_games() -> list[dict]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT
                        game_name,
                        COUNT(*) AS session_count,
                        ROUND(
                            SUM(EXTRACT(EPOCH FROM (COALESCE(ended_at, NOW()) - started_at)) / 3600.0)::numeric,
                            1
                        )::float AS total_hours
                    FROM stream_sessions
                    WHERE channel_id = $1 AND started_at >= $2 AND game_name IS NOT NULL
                    GROUP BY game_name
                    ORDER BY session_count DESC, total_hours DESC
                    LIMIT {_TOP_GAMES_LIMIT}
                    """,
                    channel_id,
                    since_date,
                )
                return [
                    {
                        "game_name": r["game_name"],
                        "session_count": int(r["session_count"]),
                        "total_hours": float(r["total_hours"]),
                    }
                    for r in rows
                ]

        async def _loyalty_tiers() -> dict:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN streak_count >= 5 THEN 1 END), 0)::int    AS core,
                        COALESCE(SUM(CASE WHEN streak_count BETWEEN 2 AND 4 THEN 1 END), 0)::int AS regular,
                        COALESCE(SUM(CASE WHEN streak_count = 1 THEN 1 END), 0)::int     AS newcomer
                    FROM viewer_attendance_streaks
                    WHERE channel_id = $1
                    """,
                    channel_id,
                )
                return {
                    "core": int(row["core"]),
                    "regular": int(row["regular"]),
                    "newcomer": int(row["newcomer"]),
                }

        (
            summary,
            top_chatters,
            top_commands,
            session_chart,
            top_games,
            loyalty_tiers,
        ) = await asyncio.gather(
            _summary(),
            _top_chatters(),
            _top_commands(),
            _session_chart(),
            _top_games(),
            _loyalty_tiers(),
        )
        return {
            **summary,
            "top_chatters": top_chatters,
            "top_commands": top_commands,
            "session_chart": session_chart,
            "top_games": top_games,
            "loyalty_tiers": loyalty_tiers,
        }
