"""Repository for game_queue_entries and game_queue_settings tables."""

from __future__ import annotations

import logging

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.game_queue import GameQueueEntry, GameQueueSettings

logger = logging.getLogger(__name__)

_ENTRY_COLUMNS = (
    "id, channel_id, user_id, user_name, redeemed_at, removed_at, removal_reason, created_at"
)

_SETTINGS_COLUMNS = "id, channel_id, group_size, enabled, created_at, updated_at"

# Short TTL cache for settings only (entries change too frequently)
_settings_cache = AsyncTTLCache(maxsize=32, ttl=300)


class GameQueueRepository:
    """Pure SQL operations for game_queue_entries."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def add_entry(self, channel_id: str, user_id: str, user_name: str) -> GameQueueEntry:
        """Add a user to the queue. Raises UniqueViolationError on duplicate."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO game_queue_entries (channel_id, user_id, user_name)
                VALUES ($1, $2, $3)
                RETURNING {_ENTRY_COLUMNS}
                """,
                channel_id,
                user_id,
                user_name,
            )
            return GameQueueEntry(**dict(row))

    async def get_active_entries(self, channel_id: str) -> list[GameQueueEntry]:
        """Get all active (not removed) entries ordered by redeemed_at ASC."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_ENTRY_COLUMNS} FROM game_queue_entries "
                "WHERE channel_id = $1 AND removed_at IS NULL "
                "ORDER BY redeemed_at ASC",
                channel_id,
            )
            return [GameQueueEntry(**dict(row)) for row in rows]

    async def find_active_by_user(self, channel_id: str, user_id: str) -> GameQueueEntry | None:
        """Find an active entry for a specific user."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_ENTRY_COLUMNS} FROM game_queue_entries "
                "WHERE channel_id = $1 AND user_id = $2 AND removed_at IS NULL",
                channel_id,
                user_id,
            )
            if not row:
                return None
            return GameQueueEntry(**dict(row))

    async def count_active(self, channel_id: str) -> int:
        """Count active entries in the queue."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM game_queue_entries "
                "WHERE channel_id = $1 AND removed_at IS NULL",
                channel_id,
            )

    async def remove_entry(self, entry_id: int, channel_id: str, reason: str = "kicked") -> bool:
        """Remove a single entry by ID. Returns True if removed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE game_queue_entries "
                "SET removed_at = NOW(), removal_reason = $3 "
                "WHERE id = $1 AND channel_id = $2 AND removed_at IS NULL",
                entry_id,
                channel_id,
                reason,
            )
            return result == "UPDATE 1"

    async def remove_by_user(self, channel_id: str, user_id: str, reason: str = "kicked") -> bool:
        """Remove an active entry by user_id. Returns True if removed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE game_queue_entries "
                "SET removed_at = NOW(), removal_reason = $3 "
                "WHERE channel_id = $1 AND user_id = $2 AND removed_at IS NULL",
                channel_id,
                user_id,
                reason,
            )
            return result == "UPDATE 1"

    async def complete_batch(
        self, channel_id: str, entry_ids: list[int], reason: str = "completed"
    ) -> int:
        """Mark a batch of entries as completed. Returns count of updated rows."""
        if not entry_ids:
            return 0
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE game_queue_entries "
                "SET removed_at = NOW(), removal_reason = $3 "
                "WHERE channel_id = $1 AND id = ANY($2) AND removed_at IS NULL",
                channel_id,
                entry_ids,
                reason,
            )
            # result is like "UPDATE N"
            return int(result.split()[-1])

    async def clear_queue(self, channel_id: str, reason: str = "cleared") -> int:
        """Clear all active entries. Returns count of cleared rows."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE game_queue_entries "
                "SET removed_at = NOW(), removal_reason = $2 "
                "WHERE channel_id = $1 AND removed_at IS NULL",
                channel_id,
                reason,
            )
            return int(result.split()[-1])


class GameQueueSettingsRepository:
    """Pure SQL operations for game_queue_settings."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_settings_cache,
        key_func=lambda self, channel_id: f"gq_settings:{channel_id}",
    )
    async def get_or_create(self, channel_id: str) -> GameQueueSettings:
        """Get settings for a channel, creating defaults if not exists."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO game_queue_settings (channel_id)
                VALUES ($1)
                ON CONFLICT (channel_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
            )
            return GameQueueSettings(**dict(row))

    async def update_settings(
        self,
        channel_id: str,
        *,
        group_size: int | None = None,
        enabled: bool | None = None,
    ) -> GameQueueSettings:
        """Update settings. Only provided fields are updated."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO game_queue_settings (channel_id, group_size, enabled)
                VALUES ($1, COALESCE($2, 4), COALESCE($3, TRUE))
                ON CONFLICT (channel_id) DO UPDATE SET
                    group_size = COALESCE($2, game_queue_settings.group_size),
                    enabled = COALESCE($3, game_queue_settings.enabled)
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                group_size,
                enabled,
            )
            result = GameQueueSettings(**dict(row))
            _settings_cache.invalidate(f"gq_settings:{channel_id}")
            return result
