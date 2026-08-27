"""Per-session detail queries for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import asyncpg


class _SessionQueryMixin:
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
