"""Manual collab-marking and conversion-attribution queries for AnalyticsRepository.

Matcher's overlap tables answer "who might I reach"; this answers "did a
specific collab actually convert anyone" — something third-party overlap
tools can't do since they don't have access to a channel's own
follow/subscribe/chat data.
"""

from __future__ import annotations

from datetime import timedelta

import asyncpg

_COLLAB_ATTRIBUTION_DAYS = 14


class _AnalyticsCollabMixin:
    pool: asyncpg.Pool

    async def create_collab_event(
        self,
        home_channel_id: str,
        partner_channel_id: str,
        window_days: int,
        note: str | None,
    ) -> dict:
        """Mark a collab now and freeze the current exclusive-to-partner
        audience as its conversion-tracking targets.

        The snapshot is taken from channel_overlap_viewers as it stands at
        this moment; later refreshes of that table must not change who counts
        as a target for this collab.
        """
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO matcher_collab_events
                    (home_channel_id, partner_channel_id, window_days, note)
                VALUES ($1, $2, $3, $4)
                RETURNING id, occurred_at, note, window_days, created_at
                """,
                home_channel_id,
                partner_channel_id,
                window_days,
                note,
            )
            collab_id = row["id"]
            await conn.execute(
                """
                INSERT INTO matcher_collab_targets (collab_id, user_id, username)
                SELECT $1, user_id, username
                FROM channel_overlap_viewers
                WHERE home_channel_id = $2
                  AND partner_channel_id = $3
                  AND window_days = $4
                  AND home_sessions = 0
                """,
                collab_id,
                home_channel_id,
                partner_channel_id,
                window_days,
            )
            target_count = await conn.fetchval(
                "SELECT COUNT(*) FROM matcher_collab_targets WHERE collab_id = $1",
                collab_id,
            )

        return {**dict(row), "target_count": int(target_count or 0)}

    async def list_collab_events(self, home_channel_id: str, partner_channel_id: str) -> list[dict]:
        """Return every collab marked for this partner with its live-computed
        conversion counts (follow / subscribe / returned-to-chat within the
        14-day attribution window, plus a "converted at least one way" union).
        """
        async with self.pool.acquire() as conn:
            collabs = await conn.fetch(
                """
                SELECT id, occurred_at, note, window_days, created_at
                FROM matcher_collab_events
                WHERE home_channel_id = $1 AND partner_channel_id = $2
                ORDER BY occurred_at DESC
                """,
                home_channel_id,
                partner_channel_id,
            )
            results: list[dict] = []
            for collab in collabs:
                attribution_ends_at = collab["occurred_at"] + timedelta(
                    days=_COLLAB_ATTRIBUTION_DAYS
                )
                stats = await conn.fetchrow(
                    """
                    WITH targets AS (
                        SELECT user_id FROM matcher_collab_targets WHERE collab_id = $1
                    ),
                    followed AS (
                        SELECT DISTINCT se.user_id
                        FROM stream_events se
                        JOIN targets t USING (user_id)
                        WHERE se.channel_id = $2 AND se.event_type = 'follow'
                          AND se.occurred_at BETWEEN $3 AND $4
                    ),
                    subscribed AS (
                        SELECT DISTINCT se.user_id
                        FROM stream_events se
                        JOIN targets t USING (user_id)
                        WHERE se.channel_id = $2 AND se.event_type = 'subscribe'
                          AND se.occurred_at BETWEEN $3 AND $4
                    ),
                    returned AS (
                        SELECT DISTINCT cs.user_id
                        FROM chatter_stats cs
                        JOIN targets t USING (user_id)
                        WHERE cs.channel_id = $2
                          AND cs.last_message_at BETWEEN $3 AND $4
                    )
                    SELECT
                        (SELECT COUNT(*) FROM targets)     AS target_count,
                        (SELECT COUNT(*) FROM followed)    AS followed_count,
                        (SELECT COUNT(*) FROM subscribed)  AS subscribed_count,
                        (SELECT COUNT(*) FROM returned)    AS returned_count,
                        (SELECT COUNT(*) FROM (
                            SELECT user_id FROM followed
                            UNION SELECT user_id FROM subscribed
                            UNION SELECT user_id FROM returned
                        ) u)                                AS converted_any_count
                    """,
                    collab["id"],
                    home_channel_id,
                    collab["occurred_at"],
                    attribution_ends_at,
                )
                target_count = int(stats["target_count"] or 0)
                converted = int(stats["converted_any_count"] or 0)
                results.append(
                    {
                        **dict(collab),
                        "target_count": target_count,
                        "followed_count": int(stats["followed_count"] or 0),
                        "subscribed_count": int(stats["subscribed_count"] or 0),
                        "returned_count": int(stats["returned_count"] or 0),
                        "converted_any_count": converted,
                        "converted_pct": round(converted / target_count * 100, 1)
                        if target_count
                        else 0.0,
                        "attribution_ends_at": attribution_ends_at,
                    }
                )
            return results

    async def delete_collab_event(self, home_channel_id: str, collab_id: int) -> bool:
        """Delete a collab mark (and its targets, via ON DELETE CASCADE). Returns
        True if a row was actually deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM matcher_collab_events WHERE id = $1 AND home_channel_id = $2",
                collab_id,
                home_channel_id,
            )
            return result != "DELETE 0"
