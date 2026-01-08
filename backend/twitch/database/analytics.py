from datetime import datetime
from typing import Optional

import asyncpg


class AnalyticsDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_session(
        self,
        channel_id: str,
        started_at: datetime,
        title: Optional[str] = None,
        game_name: Optional[str] = None
    ) -> int:
        async with self.pool.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO stream_sessions (channel_id, started_at, title, game_name)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                channel_id, started_at, title, game_name
            )
            if session_id is None:
                raise ValueError("Failed to create session: no ID returned")
            return int(session_id)

    async def get_active_session(self, channel_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, channel_id, started_at, ended_at, title, game_name
                FROM stream_sessions
                WHERE channel_id = $1 AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                channel_id
            )
            return dict(row) if row else None

    async def end_session(self, session_id: int, ended_at: datetime) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stream_sessions
                SET ended_at = $1
                WHERE id = $2
                """,
                ended_at, session_id
            )

    async def record_command_usage(
        self,
        session_id: int,
        channel_id: str,
        command_name: str
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO command_stats (session_id, channel_id, command_name, usage_count, last_used_at)
                VALUES ($1, $2, $3, 1, NOW())
                ON CONFLICT (session_id, command_name)
                DO UPDATE SET
                    usage_count = command_stats.usage_count + 1,
                    last_used_at = NOW()
                """,
                session_id, channel_id, command_name
            )

    async def record_follow_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: Optional[str],
        occurred_at: datetime
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events (session_id, channel_id, event_type, user_id, username, display_name, occurred_at)
                VALUES ($1, $2, 'follow', $3, $4, $5, $6)
                """,
                session_id, channel_id, user_id, username, display_name, occurred_at
            )

    async def record_subscribe_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: Optional[str],
        tier: str,
        is_gift: bool,
        occurred_at: datetime
    ) -> None:
        metadata = {"tier": tier, "is_gift": is_gift}

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
                VALUES ($1, $2, 'subscribe', $3, $4, $5, $6, $7)
                """,
                session_id, channel_id, user_id, username, display_name, metadata, occurred_at
            )

    async def record_raid_event(
        self,
        session_id: int,
        channel_id: str,
        from_broadcaster_id: str,
        from_broadcaster_name: str,
        viewers: int,
        occurred_at: datetime
    ) -> None:
        metadata = {
            "viewers": viewers,
            "from_broadcaster_id": from_broadcaster_id,
            "from_broadcaster_name": from_broadcaster_name
        }

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events (session_id, channel_id, event_type, user_id, username, metadata, occurred_at)
                VALUES ($1, $2, 'raid', $3, $4, $5, $6)
                """,
                session_id, channel_id, from_broadcaster_id, from_broadcaster_name, metadata, occurred_at
            )
