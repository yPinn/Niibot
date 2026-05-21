"""Overlap computation queries for AnalyticsRepository."""

from __future__ import annotations

import logging

import asyncpg

LOGGER = logging.getLogger(__name__)


class _AnalyticsOverlapMixin:
    pool: asyncpg.Pool

    async def refresh_overlap(self, home_channel_id: str, days: int = 30) -> int:
        """Recompute overlap for all partner channels. Returns count of partner channels processed."""
        async with self.pool.acquire() as conn:
            partner_rows = await conn.fetch(
                """
                SELECT DISTINCT channel_id
                FROM chatter_stats
                WHERE channel_id != $1
                  AND last_message_at >= NOW() - ($2 * INTERVAL '1 day')
                """,
                home_channel_id,
                days,
            )
            count = 0
            for row in partner_rows:
                partner_id = row["channel_id"]
                try:
                    await self._compute_channel_overlap(conn, home_channel_id, partner_id, days)
                    count += 1
                except Exception:
                    LOGGER.warning(
                        "Failed to compute overlap for partner %s", partner_id, exc_info=True
                    )
            return count

    async def _compute_channel_overlap(
        self,
        conn: asyncpg.Connection,
        home_channel_id: str,
        partner_channel_id: str,
        days: int,
    ) -> None:
        """Compute and upsert overlap data for a single partner channel."""
        viewer_rows = await conn.fetch(
            """
            WITH partner_chatters AS (
                SELECT
                    cs.user_id,
                    MAX(cs.username)      AS username,
                    MAX(cs.display_name)  AS display_name,
                    COUNT(DISTINCT cs.session_id)::SMALLINT  AS sessions,
                    COALESCE(SUM(cs.message_count), 0)       AS messages,
                    COALESCE(SUM(cs.watch_seconds), 0)       AS watch_sec,
                    MAX(cs.last_message_at)                  AS last_seen
                FROM chatter_stats cs
                WHERE cs.channel_id = $1
                  AND cs.last_message_at >= NOW() - ($3 * INTERVAL '1 day')
                GROUP BY cs.user_id
            ),
            home_chatters AS (
                SELECT
                    cs.user_id,
                    COUNT(DISTINCT cs.session_id)::SMALLINT  AS sessions,
                    COALESCE(SUM(cs.message_count), 0)       AS messages
                FROM chatter_stats cs
                WHERE cs.channel_id = $2
                  AND cs.last_message_at >= NOW() - ($3 * INTERVAL '1 day')
                GROUP BY cs.user_id
            )
            SELECT
                pc.user_id,
                pc.username,
                pc.display_name,
                pc.sessions                        AS partner_sessions,
                pc.messages                        AS partner_messages,
                pc.watch_sec                       AS partner_watch_sec,
                pc.last_seen                       AS partner_last_seen,
                COALESCE(hc.sessions, 0)::SMALLINT AS home_sessions,
                COALESCE(hc.messages, 0)           AS home_messages,
                ROUND(
                    (
                        (pc.sessions * 3.0
                         + LN(GREATEST(pc.messages, 1)) * 1.5
                         + (pc.watch_sec / 3600.0) * 0.5)
                        * CASE
                            WHEN hc.user_id IS NULL THEN 1.0
                            WHEN hc.sessions < 3    THEN 0.5
                            ELSE                         0.1
                          END
                    )::numeric
                , 2) AS potential_score
            FROM partner_chatters pc
            LEFT JOIN home_chatters hc ON pc.user_id = hc.user_id
            """,
            partner_channel_id,
            home_channel_id,
            days,
        )

        if not viewer_rows:
            return

        # Upsert viewers
        await conn.executemany(
            """
            INSERT INTO channel_overlap_viewers (
                home_channel_id, partner_channel_id, user_id,
                username, display_name,
                partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
                home_sessions, home_messages, potential_score, computed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
            ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
                username          = EXCLUDED.username,
                display_name      = EXCLUDED.display_name,
                partner_sessions  = EXCLUDED.partner_sessions,
                partner_messages  = EXCLUDED.partner_messages,
                partner_watch_sec = EXCLUDED.partner_watch_sec,
                partner_last_seen = EXCLUDED.partner_last_seen,
                home_sessions     = EXCLUDED.home_sessions,
                home_messages     = EXCLUDED.home_messages,
                potential_score   = EXCLUDED.potential_score,
                computed_at       = NOW()
            """,
            [
                (
                    home_channel_id,
                    partner_channel_id,
                    r["user_id"],
                    r["username"],
                    r["display_name"],
                    r["partner_sessions"],
                    r["partner_messages"],
                    r["partner_watch_sec"],
                    r["partner_last_seen"],
                    r["home_sessions"],
                    r["home_messages"],
                    r["potential_score"],
                )
                for r in viewer_rows
            ],
        )

        # Compute summary stats
        partner_total = len(viewer_rows)
        shared = sum(1 for r in viewer_rows if r["home_sessions"] > 0)
        exclusive = partner_total - shared
        home_total_row = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM chatter_stats
            WHERE channel_id = $1
              AND last_message_at >= NOW() - ($2 * INTERVAL '1 day')
            """,
            home_channel_id,
            days,
        )
        home_total = int(home_total_row or 0)
        overlap_pct = round((shared / partner_total * 100), 2) if partner_total else 0.0

        await conn.execute(
            """
            INSERT INTO channel_overlap_summary (
                home_channel_id, partner_channel_id, window_days,
                partner_unique_chatters, home_unique_chatters,
                shared_chatters, exclusive_to_partner, overlap_pct, computed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (home_channel_id, partner_channel_id, window_days) DO UPDATE SET
                partner_unique_chatters = EXCLUDED.partner_unique_chatters,
                home_unique_chatters    = EXCLUDED.home_unique_chatters,
                shared_chatters         = EXCLUDED.shared_chatters,
                exclusive_to_partner    = EXCLUDED.exclusive_to_partner,
                overlap_pct             = EXCLUDED.overlap_pct,
                computed_at             = NOW()
            """,
            home_channel_id,
            partner_channel_id,
            days,
            partner_total,
            home_total,
            shared,
            exclusive,
            overlap_pct,
        )

    async def get_matcher_summaries(self, home_channel_id: str, days: int = 30) -> list[dict]:
        """Return per-partner channel summary rows."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    partner_channel_id,
                    partner_unique_chatters,
                    home_unique_chatters,
                    shared_chatters,
                    exclusive_to_partner,
                    overlap_pct,
                    computed_at
                FROM channel_overlap_summary
                WHERE home_channel_id = $1
                  AND window_days = $2
                ORDER BY exclusive_to_partner DESC
                """,
                home_channel_id,
                days,
            )
            return [dict(r) for r in rows]

    async def get_partner_session_stats(self, partner_channel_id: str, days: int = 90) -> dict:
        """Return top games, peak hours, session count, and avg duration from stream_sessions."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    game_name,
                    EXTRACT(HOUR FROM started_at AT TIME ZONE 'Asia/Taipei')::INT AS start_hour,
                    GREATEST(
                        EXTRACT(EPOCH FROM COALESCE(ended_at - started_at, INTERVAL '0')) / 3600.0,
                        0
                    ) AS duration_hours
                FROM stream_sessions
                WHERE channel_id = $1
                  AND started_at >= NOW() - ($2 * INTERVAL '1 day')
                ORDER BY started_at
                """,
                partner_channel_id,
                days,
            )
            if not rows:
                return {
                    "top_games": [],
                    "peak_hours": [],
                    "session_count": 0,
                    "avg_stream_hours": 0.0,
                }

            game_counts: dict[str, int] = {}
            hours: list[int] = []
            durations: list[float] = []
            for row in rows:
                if row["game_name"]:
                    game_counts[row["game_name"]] = game_counts.get(row["game_name"], 0) + 1
                hours.append(int(row["start_hour"]))
                durations.append(float(row["duration_hours"]))

            top_games = sorted(game_counts, key=lambda g: game_counts[g], reverse=True)[:3]
            avg_hours = round(sum(durations) / len(durations), 1) if durations else 0.0

            return {
                "top_games": top_games,
                "peak_hours": sorted(set(hours)),
                "session_count": len(rows),
                "avg_stream_hours": avg_hours,
            }

    async def get_potential_viewers(
        self,
        home_channel_id: str,
        partner_channel_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """Return (total_count, viewer_rows) sorted by potential_score DESC."""
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM channel_overlap_viewers
                WHERE home_channel_id = $1 AND partner_channel_id = $2
                """,
                home_channel_id,
                partner_channel_id,
            )
            rows = await conn.fetch(
                """
                SELECT
                    user_id, username, display_name,
                    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
                    home_sessions, home_messages, potential_score, computed_at
                FROM channel_overlap_viewers
                WHERE home_channel_id = $1 AND partner_channel_id = $2
                ORDER BY potential_score DESC
                LIMIT $3 OFFSET $4
                """,
                home_channel_id,
                partner_channel_id,
                limit,
                offset,
            )
            return int(total or 0), [dict(r) for r in rows]
