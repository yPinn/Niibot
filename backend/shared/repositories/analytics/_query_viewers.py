"""Viewer-level analytics queries for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import asyncpg
from asyncpg.exceptions import UndefinedTableError

from shared.repositories.analytics import _query_common
from shared.repositories.analytics._query_common import (
    _SCORE_SQL,
    _STREAK_CTE,
    _STREAK_CTE_EMPTY,
)

LOGGER = logging.getLogger(__name__)

# Twitch Plus Program: 100 pts -> 60/40 split, 300 pts -> 70/30.
_PLUS_TIER1_POINTS = 100
_PLUS_TIER2_POINTS = 300


def _plus_plan(points: int) -> str:
    if points >= _PLUS_TIER2_POINTS:
        return "70/30"
    if points >= _PLUS_TIER1_POINTS:
        return "60/40"
    return "50/50"


# sub_tier is not guaranteed to be T1/T2/T3 — the dev seed writes "2", tier_label
# lets unknown codes through, so legacy rows may hold "1000". Cover every form;
# an unrecognised tier falls to Tier 1 weight.
_PLUS_ESTIMATE_SQL = """
SELECT
    COALESCE(SUM(pts) FILTER (WHERE paid_known), 0)::int AS confirmed_points,
    COUNT(*) FILTER (WHERE paid_known)                   AS confirmed_subs,
    COALESCE(SUM(pts) FILTER (WHERE pending), 0)::int    AS pending_points,
    COUNT(*) FILTER (WHERE pending)                      AS pending_subs,
    COUNT(*) FILTER (WHERE paid_known AND tier = 1)      AS t1,
    COUNT(*) FILTER (WHERE paid_known AND tier = 2)      AS t2,
    COUNT(*) FILTER (WHERE paid_known AND tier = 3)      AS t3,
    MAX(updated_at)                                      AS data_as_of
FROM (
    SELECT
        CASE
            WHEN sub_tier IN ('T3', '3000', '3') THEN 3
            WHEN sub_tier IN ('T2', '2000', '2') THEN 2
            ELSE 1
        END AS tier,
        CASE
            WHEN sub_tier IN ('T3', '3000', '3') THEN 6
            WHEN sub_tier IN ('T2', '2000', '2') THEN 2
            ELSE 1
        END AS pts,
        (COALESCE(sub_gifted, FALSE) = FALSE AND sub_is_prime = FALSE)  AS paid_known,
        (COALESCE(sub_gifted, FALSE) = FALSE AND sub_is_prime IS NULL)  AS pending,
        updated_at
    FROM viewer_channel_status
    WHERE channel_id = $1 AND is_subscribed = TRUE
) t
"""


class _ViewerQueryMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

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
                chatter_base AS MATERIALIZED (
                    SELECT
                        c.user_id, c.username, c.display_name,
                        c.message_count, c.session_id, c.watch_seconds, c.last_message_at
                    FROM chatter_stats c
                    WHERE c.channel_id = $1
                      AND c.session_id IN (SELECT id FROM session_scope)
                      AND c.user_id != $1
                      AND lower(c.username) != ALL($4::text[])
                ),
                chatter_totals AS (
                    SELECT
                        user_id,
                        SUM(message_count)         AS total_messages,
                        COUNT(DISTINCT session_id) AS sessions_attended,
                        MAX(last_message_at)        AS last_seen,
                        SUM(watch_seconds)          AS watch_seconds
                    FROM chatter_base
                    GROUP BY user_id
                ),
                latest_name AS (
                    SELECT DISTINCT ON (user_id)
                        user_id, username, display_name
                    FROM chatter_base
                    ORDER BY user_id, last_message_at DESC
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

        args = (channel_id, since_date, limit, await _query_common._get_bot_list())
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

        args = (channel_id, user_id, month_start, await _query_common._get_bot_list())
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

    async def get_plus_program_estimate(self, channel_id: str) -> dict:
        """Single-month Twitch Plus Program point estimate from the current
        subscriber roster.

        Gifted and Prime subs earn no points. A sub whose Prime status has never
        been observed via ``channel.chat.notification`` (``sub_is_prime IS NULL``)
        is reported as *pending* rather than assumed paid, so ``confirmed_points``
        is a floor and ``confirmed + pending`` a ceiling.
        """
        empty: dict = {
            "confirmed_points": 0,
            "confirmed_subs": 0,
            "pending_points": 0,
            "pending_subs": 0,
            "tier_breakdown": {"t1": 0, "t2": 0, "t3": 0},
            "plan_confirmed": "50/50",
            "plan_ceiling": "50/50",
            "data_as_of": None,
        }
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(_PLUS_ESTIMATE_SQL, channel_id)
        except (UndefinedTableError, asyncpg.exceptions.UndefinedColumnError):
            return empty
        if row is None:
            return empty

        confirmed = int(row["confirmed_points"])
        pending = int(row["pending_points"])
        return {
            "confirmed_points": confirmed,
            "confirmed_subs": int(row["confirmed_subs"]),
            "pending_points": pending,
            "pending_subs": int(row["pending_subs"]),
            "tier_breakdown": {
                "t1": int(row["t1"]),
                "t2": int(row["t2"]),
                "t3": int(row["t3"]),
            },
            "plan_confirmed": _plus_plan(confirmed),
            "plan_ceiling": _plus_plan(confirmed + pending),
            "data_as_of": row["data_as_of"],
        }
