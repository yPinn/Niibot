"""Event recording and chatter-stats operations for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import logging
from datetime import datetime

import asyncpg

LOGGER: logging.Logger = logging.getLogger(__name__)


class _AnalyticsEventsMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

    # ==================== Stream event recording ====================

    async def record_command_usage(
        self, session_id: int, channel_id: str, command_name: str
    ) -> None:
        """Increment (or create) a command usage counter for a session."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO command_stats (session_id, channel_id, command_name, usage_count, last_used_at)
                VALUES ($1, $2, $3, 1, NOW())
                ON CONFLICT (session_id, command_name)
                DO UPDATE SET
                    usage_count  = command_stats.usage_count + 1,
                    last_used_at = NOW()
                """,
                session_id,
                channel_id,
                command_name,
            )

    async def record_follow_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        occurred_at: datetime,
    ) -> None:
        """Record a follow event."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, display_name, occurred_at)
                VALUES ($1, $2, 'follow', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                display_name,
                occurred_at,
            )

    async def record_subscribe_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        tier: str,
        is_gift: bool,
        occurred_at: datetime,
    ) -> None:
        """Record a subscribe event."""
        metadata = {"tier": tier, "is_gift": is_gift}
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
                VALUES ($1, $2, 'subscribe', $3, $4, $5, $6, $7)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                display_name,
                metadata,
                occurred_at,
            )

    async def record_raid_event(
        self,
        session_id: int,
        channel_id: str,
        from_broadcaster_id: str,
        from_broadcaster_name: str,
        viewers: int,
        occurred_at: datetime,
    ) -> None:
        """Record a raid event."""
        metadata = {
            "viewers": viewers,
            "from_broadcaster_id": from_broadcaster_id,
            "from_broadcaster_name": from_broadcaster_name,
        }
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, metadata, occurred_at)
                VALUES ($1, $2, 'raid', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                from_broadcaster_id,
                from_broadcaster_name,
                metadata,
                occurred_at,
            )

    # ==================== Chatter stats ====================

    async def flush_chatter_stats(
        self,
        session_id: int,
        channel_id: str,
        chatters: dict[str, dict],
    ) -> None:
        """Batch-insert chatter stats for a completed session.

        Args:
            chatters: {user_id: {"username": str, "display_name": str | None, "count": int, "last_at": datetime}}
        """
        if not chatters:
            return

        rows = [
            (
                session_id,
                channel_id,
                user_id,
                data["username"],
                data.get("display_name"),
                data["count"],
                data["last_at"],
            )
            for user_id, data in chatters.items()
        ]

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO chatter_stats
                    (session_id, channel_id, user_id, username, display_name, message_count, last_message_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (session_id, user_id) DO UPDATE SET
                    username        = EXCLUDED.username,
                    display_name    = EXCLUDED.display_name,
                    message_count   = EXCLUDED.message_count,
                    last_message_at = EXCLUDED.last_message_at
                """,
                rows,
            )

        LOGGER.info(f"Flushed chatter stats for session {session_id}: {len(rows)} chatters")
