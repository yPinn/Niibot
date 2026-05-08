"""Aggregation read queries for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
from asyncpg.exceptions import UndefinedTableError

from shared.cache import cached
from shared.repositories.analytics._caches import (
    _summary_cache,
    _top_chatters_cache,
    _top_commands_cache,
)

LOGGER = logging.getLogger(__name__)

_KNOWN_BOTS: frozenset[str] = frozenset(
    {
        "nightbot",
        "streamlabs",
        "streamelements",
        "moobot",
        "wizebot",
        "fossabot",
        "commanderroot",
        "electricallongboard",
        "sery_bot",
        "soundalerts",
        "pokemoncommunitygame",
        "bingothemighty",
        "kofistreambot",
        "rogueg1rl",
        "stay_hydrated_bot",
        "anotherttvviewer",
        "own3d",
        "pretzel_rocks",
        "streambeats",
        "rainmaker",
        "streamholics",
        "revlobot",
        "botisimo",
        "p0sitivitybot",
        "lurxx",
        "streamloots",
        "fireside_bot",
        "streamcapturebot",
        "staysafe_bot",
        "dinks_bot",
        "marbiebot",
        "dixpermit",
        "playwithviewers",
        "niibot_",
        "chiwabots",
    }
)

_bot_cache: frozenset[str] = frozenset()
_bot_cache_ts: float = 0.0
_BOT_CACHE_TTL: float = 86400.0  # 24 hours


async def _get_bot_list() -> list[str]:
    """Return merged bot list: manual _KNOWN_BOTS + TwitchInsights (cached 24h)."""
    global _bot_cache, _bot_cache_ts
    if _bot_cache and time.monotonic() - _bot_cache_ts < _BOT_CACHE_TTL:
        return list(_KNOWN_BOTS | _bot_cache)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.twitchinsights.net/v1/bots/all")
            resp.raise_for_status()
            data = resp.json()
            _bot_cache = frozenset(entry[0].lower() for entry in data.get("bots", []))
            _bot_cache_ts = time.monotonic()
            LOGGER.info("Fetched %d bots from TwitchInsights", len(_bot_cache))
    except Exception as exc:
        LOGGER.warning("TwitchInsights bot list fetch failed (%s), using local list", exc)
    return list(_KNOWN_BOTS | _bot_cache)


_SCORE_SQL: str = """ROUND((
    (t.watch_seconds::numeric / 3600.0)
    + (1.5 * LN(
        LEAST(
            t.total_messages::numeric,
            GREATEST(10.0, t.watch_seconds::numeric / 30.0)
        ) + 1.0
      ))
    + (0.5 * LN(t.sessions_attended::numeric + 1.0))
    + COALESCE(eb.sub_tier_bonus, 0.0)
    + (2.0 * LN(COALESCE(eb.total_bits, 0)::numeric / 100.0 + 1.0))
) * (1.0 + LEAST(COALESCE(sk.streak_count, 0), 20) * 0.05)
  * CASE
      WHEN t.last_seen >= NOW() - INTERVAL '30 days' THEN 1.0
      WHEN t.last_seen >= NOW() - INTERVAL '60 days' THEN 0.75
      ELSE 0.5
    END
, 2)::float"""

_STREAK_CTE: str = """streak_data AS (
    SELECT user_id, streak_count
    FROM viewer_attendance_streaks
    WHERE channel_id = $1
)"""

_STREAK_CTE_EMPTY: str = (
    "streak_data AS (SELECT NULL::text AS user_id, 0::int AS streak_count WHERE FALSE)"
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
                      AND c.user_id != $1
                    ORDER BY c.user_id, c.last_message_at DESC
                ),
                totals AS (
                    SELECT c.user_id, SUM(c.message_count) AS total_messages
                    FROM chatter_stats c
                    JOIN stream_sessions s ON s.id = c.session_id
                    WHERE c.channel_id = $1 AND s.started_at >= $2
                      AND c.user_id != $1
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
                  AND c.user_id != $1
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
        bots = await _get_bot_list()

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
                    """
                    WITH totals AS (
                        SELECT c.user_id, SUM(c.message_count) AS total
                        FROM chatter_stats c
                        JOIN stream_sessions s ON s.id = c.session_id
                        WHERE c.channel_id = $1 AND s.started_at >= $2
                          AND c.user_id != $1
                          AND lower(c.username) != ALL($3::text[])
                        GROUP BY c.user_id
                    ),
                    latest_name AS (
                        SELECT DISTINCT ON (c.user_id) c.user_id, c.username, c.display_name
                        FROM chatter_stats c
                        JOIN stream_sessions s ON s.id = c.session_id
                        WHERE c.channel_id = $1 AND s.started_at >= $2
                          AND c.user_id != $1
                          AND lower(c.username) != ALL($3::text[])
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

        def _q(streak_cte: str, include_status: bool = True) -> str:
            status_select = (
                """
                    COALESCE(vcs.is_subscribed, FALSE)      AS is_subscribed,
                    vcs.sub_tier,
                    COALESCE(vcs.is_mod, FALSE)             AS is_mod,
                    COALESCE(vcs.is_vip, FALSE)             AS is_vip,
                    vcs.follow_since,
                    COALESCE(vcs.total_gifts_given, 0)      AS total_gifts_given"""
                if include_status
                else """
                    FALSE       AS is_subscribed,
                    NULL::text  AS sub_tier,
                    FALSE       AS is_mod,
                    FALSE       AS is_vip,
                    NULL::timestamptz AS follow_since,
                    0           AS total_gifts_given"""
            )
            status_join = (
                """
                LEFT JOIN viewer_channel_status vcs
                    ON vcs.channel_id = $1 AND vcs.user_id = t.user_id"""
                if include_status
                else ""
            )
            return f"""
                WITH session_scope AS MATERIALIZED (
                    SELECT id FROM stream_sessions
                    WHERE channel_id = $1 AND started_at >= $2
                ),
                chatter_totals AS (
                    SELECT
                        c.user_id,
                        SUM(c.message_count)         AS total_messages,
                        COUNT(DISTINCT c.session_id) AS sessions_attended,
                        MAX(c.last_message_at)        AS last_seen,
                        SUM(c.watch_seconds)          AS watch_seconds
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                      AND c.user_id != $1
                      AND lower(c.username) != ALL($4::text[])
                    GROUP BY c.user_id
                ),
                latest_name AS (
                    SELECT DISTINCT ON (c.user_id)
                        c.user_id, c.username, c.display_name
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                      AND c.user_id != $1
                      AND lower(c.username) != ALL($4::text[])
                    ORDER BY c.user_id, c.last_message_at DESC
                ),
                event_bonuses AS (
                    SELECT user_id,
                        SUM(CASE WHEN event_type = 'cheer' THEN (metadata->>'bits')::int ELSE 0 END) AS total_bits,
                        MAX(CASE
                            WHEN event_type = 'subscribe' AND (metadata->>'tier') = '3000' THEN 10.0
                            WHEN event_type = 'subscribe' AND (metadata->>'tier') = '2000' THEN 7.0
                            WHEN event_type = 'subscribe' THEN 5.0
                            ELSE 0.0
                        END) AS sub_tier_bonus
                    FROM stream_events
                    WHERE channel_id = $1
                      AND event_type IN ('cheer', 'subscribe')
                      AND user_id IS NOT NULL
                      AND session_id IN (SELECT id FROM session_scope)
                    GROUP BY user_id
                ),
                {streak_cte}
                SELECT
                    n.user_id,
                    n.username,
                    n.display_name,
                    t.total_messages,
                    t.sessions_attended,
                    t.last_seen,
                    t.watch_seconds,
                    COALESCE(eb.total_bits, 0)  AS total_bits,
                    {_SCORE_SQL}                AS engagement_score,
                    {status_select}
                FROM chatter_totals t
                JOIN latest_name n ON n.user_id = t.user_id
                LEFT JOIN event_bonuses eb ON eb.user_id = t.user_id
                LEFT JOIN streak_data sk ON sk.user_id = t.user_id
                {status_join}
                ORDER BY engagement_score DESC
                LIMIT $3
                """

        args = (channel_id, since_date, limit, await _get_bot_list())
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(_q(_STREAK_CTE), *args)
        except asyncpg.exceptions.UndefinedTableError:
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(_q(_STREAK_CTE_EMPTY), *args)
            except asyncpg.exceptions.UndefinedTableError:
                try:
                    async with self.pool.acquire() as conn:
                        rows = await conn.fetch(_q(_STREAK_CTE_EMPTY, include_status=False), *args)
                except Exception:
                    LOGGER.exception(
                        "list_viewers: all fallbacks failed for channel %s", channel_id
                    )
                    return []

        return [
            {
                "user_id": r["user_id"],
                "username": r["username"],
                "display_name": r["display_name"],
                "total_messages": int(r["total_messages"]),
                "sessions_attended": int(r["sessions_attended"]),
                "last_seen": r["last_seen"],
                "watch_seconds": int(r["watch_seconds"]),
                "total_bits": int(r["total_bits"]),
                "total_gifts": int(r["total_gifts_given"]),
                "engagement_score": float(r["engagement_score"]),
                "is_subscribed": bool(r["is_subscribed"]),
                "sub_tier": r["sub_tier"],
                "is_mod": bool(r["is_mod"]),
                "is_vip": bool(r["is_vip"]),
                "follow_since": r["follow_since"],
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
                            c.watch_seconds,
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
                        MAX(last_message_at)                        AS last_seen,
                        COALESCE(SUM(watch_seconds), 0)             AS watch_seconds
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
                    "watch_seconds": int(row["watch_seconds"]),
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

        async def _status() -> dict | None:
            return await self.get_viewer_channel_status(channel_id, user_id)

        async def _follow_since_fallback() -> datetime | None:
            """Fallback: derive follow_since from stream_events for historical data."""
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

        async def _streak() -> tuple[int, int]:
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT streak_count, best_streak FROM viewer_attendance_streaks
                        WHERE channel_id = $1 AND user_id = $2
                        """,
                        channel_id,
                        user_id,
                    )
                    if not row:
                        return 0, 0
                    return int(row["streak_count"]), int(row["best_streak"])
            except asyncpg.exceptions.UndefinedTableError:
                return 0, 0
            except asyncpg.exceptions.UndefinedColumnError:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT streak_count FROM viewer_attendance_streaks "
                        "WHERE channel_id = $1 AND user_id = $2",
                        channel_id,
                        user_id,
                    )
                    return (int(row["streak_count"]) if row else 0), 0

        (
            stats,
            events,
            status,
            (streak_count, best_streak),
            follow_since_fallback,
        ) = await asyncio.gather(
            _stats(), _events(), _status(), _streak(), _follow_since_fallback()
        )
        if stats is None:
            return None

        follow_since: datetime | None = (status or {}).get("follow_since") or follow_since_fallback

        total_bits = sum(
            int((e["metadata"] or {}).get("bits", 0)) for e in events if e["event_type"] == "cheer"
        )
        total_gifts = int((status or {}).get("total_gifts_given", 0))

        return {
            "user_id": user_id,
            **stats,
            "total_bits": total_bits,
            "total_gifts": total_gifts,
            "follow_since": follow_since,
            "streak_count": streak_count,
            "best_streak": best_streak,
            "events": events,
            "channel_status": status,
        }

    async def get_viewer_session_attendance(
        self, channel_id: str, user_id: str, days: int = 30
    ) -> list[dict]:
        """Per-session attendance for a viewer within the given window.

        Returns ALL sessions in the period (including unattended ones with viewer_watch_seconds=0)
        so the heatmap can show gaps.
        """
        since_date = datetime.now(UTC) - timedelta(days=days)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    s.id AS session_id,
                    s.started_at,
                    EXTRACT(EPOCH FROM (COALESCE(s.ended_at, NOW()) - s.started_at))::int
                        AS stream_duration_seconds,
                    COALESCE(c.watch_seconds, 0) AS viewer_watch_seconds,
                    (c.user_id IS NOT NULL) AS attended
                FROM stream_sessions s
                LEFT JOIN chatter_stats c
                    ON c.session_id = s.id
                    AND c.channel_id = $1
                    AND c.user_id = $3
                WHERE s.channel_id = $1 AND s.started_at >= $2
                ORDER BY s.started_at ASC
                """,
                channel_id,
                since_date,
                user_id,
            )
        return [
            {
                "session_id": r["session_id"],
                "started_at": r["started_at"],
                "stream_duration_seconds": int(r["stream_duration_seconds"]),
                "viewer_watch_seconds": int(r["viewer_watch_seconds"]),
                "attended": bool(r["attended"]),
            }
            for r in rows
        ]

    async def get_viewer_rank(self, channel_id: str, user_id: str) -> dict | None:
        """Monthly engagement rank for a specific viewer.

        Returns rank, total_viewers, score, and key stats for the current
        calendar month (UTC). Returns None if the viewer has no data this month.
        """
        now = datetime.now(UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)

        def _q(streak_cte: str) -> str:
            return f"""
                WITH session_scope AS MATERIALIZED (
                    SELECT id FROM stream_sessions
                    WHERE channel_id = $1 AND started_at >= $3
                ),
                chatter_totals AS (
                    SELECT
                        c.user_id,
                        SUM(c.message_count)         AS total_messages,
                        COUNT(DISTINCT c.session_id) AS sessions_attended,
                        MAX(c.last_message_at)        AS last_seen,
                        SUM(c.watch_seconds)          AS watch_seconds
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                      AND c.user_id != $1
                      AND lower(c.username) != ALL($4::text[])
                    GROUP BY c.user_id
                ),
                event_bonuses AS (
                    SELECT user_id,
                        SUM(CASE WHEN event_type = 'cheer' THEN (metadata->>'bits')::int ELSE 0 END) AS total_bits,
                        MAX(CASE
                            WHEN event_type = 'subscribe' AND (metadata->>'tier') = '3000' THEN 10.0
                            WHEN event_type = 'subscribe' AND (metadata->>'tier') = '2000' THEN 7.0
                            WHEN event_type = 'subscribe' THEN 5.0
                            ELSE 0.0
                        END) AS sub_tier_bonus
                    FROM stream_events
                    WHERE channel_id = $1
                      AND event_type IN ('cheer', 'subscribe')
                      AND user_id IS NOT NULL
                      AND session_id IN (SELECT id FROM session_scope)
                    GROUP BY user_id
                ),
                {streak_cte},
                scores AS (
                    SELECT
                        t.user_id,
                        t.total_messages,
                        t.sessions_attended,
                        t.watch_seconds,
                        COALESCE(sk.streak_count, 0) AS streak_count,
                        {_SCORE_SQL} AS engagement_score
                    FROM chatter_totals t
                    LEFT JOIN event_bonuses eb ON eb.user_id = t.user_id
                    LEFT JOIN streak_data sk ON sk.user_id = t.user_id
                ),
                ranked AS (
                    SELECT *,
                        RANK() OVER (ORDER BY engagement_score DESC)::int AS rank,
                        COUNT(*) OVER ()::int AS total_viewers
                    FROM scores
                )
                SELECT * FROM ranked WHERE user_id = $2
                """

        args = (channel_id, user_id, month_start, await _get_bot_list())
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(_q(_STREAK_CTE), *args)
        except asyncpg.exceptions.UndefinedTableError:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(_q(_STREAK_CTE_EMPTY), *args)

        if not row:
            return None

        return {
            "rank": int(row["rank"]),
            "total_viewers": int(row["total_viewers"]),
            "engagement_score": float(row["engagement_score"]),
            "total_messages": int(row["total_messages"]),
            "watch_seconds": int(row["watch_seconds"]),
            "sessions_attended": int(row["sessions_attended"]),
            "streak_count": int(row["streak_count"]),
        }

    async def get_viewer_channel_status(self, channel_id: str, user_id: str) -> dict | None:
        """Read all cached status fields for a single viewer."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        is_subscribed, sub_tier, sub_gifted, sub_gifter,
                        is_mod, is_vip,
                        is_banned, ban_expires_at, ban_reason,
                        follow_since,
                        profile_image_url, offline_image_url,
                        account_created_at, broadcaster_type,
                        total_gifts_given
                    FROM viewer_channel_status
                    WHERE channel_id = $1 AND user_id = $2
                    """,
                    channel_id,
                    user_id,
                )
                return dict(row) if row else None
        except UndefinedTableError:
            return None
