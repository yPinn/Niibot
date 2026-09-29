"""Rebuild the channel-scoped active check-in streak projection."""

from __future__ import annotations

import asyncpg


async def rebuild_checkin_streaks(conn: asyncpg.Connection, channel_id: str) -> None:
    """Rebuild streaks from the ledger under the channel's current day policy."""
    await conn.execute(
        "DELETE FROM viewer_daily_checkin_streaks WHERE channel_id = $1",
        channel_id,
    )
    await conn.execute(
        """
        WITH settings AS (
            SELECT COALESCE(
                (SELECT live_only FROM checkin_settings WHERE channel_id = $1),
                TRUE
            ) AS live_only
        ), eligible_days AS (
            SELECT
                checkin_broadcast_day,
                DENSE_RANK() OVER (ORDER BY checkin_broadcast_day) AS day_ordinal
            FROM (
                SELECT DISTINCT checkin_broadcast_day
                FROM stream_sessions
                WHERE channel_id = $1
                  AND checkin_eligible
                  AND checkin_broadcast_day IS NOT NULL
            ) AS days
        ), carryover_points AS (
            SELECT
                carryover.channel_id,
                carryover.user_id,
                carryover.last_source_date AS checkin_date,
                CASE
                    WHEN settings.live_only THEN COALESCE(
                        (
                            SELECT MIN(eligible_days.day_ordinal) - 1
                            FROM eligible_days
                            WHERE eligible_days.checkin_broadcast_day
                                  > carryover.last_source_date
                        ),
                        0
                    )
                    ELSE carryover.last_source_date - DATE '1970-01-01'
                END::BIGINT AS day_ordinal,
                COALESCE(carryover.source_current_streak, 0)::BIGINT AS base_streak,
                TRUE AS is_carryover
            FROM viewer_checkin_carryovers AS carryover
            CROSS JOIN settings
            WHERE carryover.channel_id = $1
        ), ledger_points AS (
            SELECT
                checkin.channel_id,
                checkin.user_id,
                checkin.checkin_date,
                CASE
                    WHEN settings.live_only THEN eligible_days.day_ordinal
                    ELSE checkin.checkin_date - DATE '1970-01-01'
                END::BIGINT AS day_ordinal,
                0::BIGINT AS base_streak,
                FALSE AS is_carryover
            FROM (
                SELECT DISTINCT channel_id, user_id, checkin_date
                FROM viewer_checkins
                WHERE channel_id = $1
            ) AS checkin
            CROSS JOIN settings
            LEFT JOIN eligible_days
              ON eligible_days.checkin_broadcast_day = checkin.checkin_date
            WHERE NOT settings.live_only OR eligible_days.day_ordinal IS NOT NULL
        ), points AS (
            SELECT * FROM carryover_points
            UNION ALL
            SELECT * FROM ledger_points
        ), numbered AS (
            SELECT
                *,
                day_ordinal - ROW_NUMBER() OVER (
                    PARTITION BY channel_id, user_id
                    ORDER BY day_ordinal, is_carryover DESC
                ) AS island_key
            FROM points
        ), islands AS (
            SELECT
                channel_id,
                user_id,
                island_key,
                MAX(checkin_date) AS last_checkin_date,
                COUNT(*) FILTER (WHERE NOT is_carryover)::BIGINT
                    + MAX(base_streak) AS current_streak
            FROM numbered
            GROUP BY channel_id, user_id, island_key
        ), latest_island AS (
            SELECT DISTINCT ON (channel_id, user_id)
                channel_id,
                user_id,
                current_streak,
                last_checkin_date
            FROM islands
            ORDER BY channel_id, user_id, last_checkin_date DESC
        )
        INSERT INTO viewer_daily_checkin_streaks
            (channel_id, user_id, current_streak, last_checkin_date)
        SELECT channel_id, user_id, current_streak, last_checkin_date
        FROM latest_island
        """,
        channel_id,
    )
