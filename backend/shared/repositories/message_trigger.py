"""Repository for message_triggers table."""

from __future__ import annotations

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.message_trigger import MessageTriggerConfig

_trigger_list_cache = AsyncTTLCache(maxsize=32, ttl=3600)

_COLUMNS = (
    "id, channel_id, trigger_name, match_type, pattern, case_sensitive, "
    "response, min_role, cooldown, priority, enabled, created_at, updated_at"
)


class MessageTriggerRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_trigger_list_cache,
        key_func=lambda self, channel_id: f"trigger_list:{channel_id}",
    )
    async def list_enabled(self, channel_id: str) -> list[MessageTriggerConfig]:
        """Return all enabled triggers for a channel, ordered by priority DESC then id."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM message_triggers "
                "WHERE channel_id = $1 AND enabled = TRUE "
                "ORDER BY priority DESC, id",
                channel_id,
            )
            return [MessageTriggerConfig(**dict(row)) for row in rows]

    async def list_all(self, channel_id: str) -> list[MessageTriggerConfig]:
        """Return all triggers for a channel (enabled + disabled)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM message_triggers "
                "WHERE channel_id = $1 ORDER BY priority DESC, id",
                channel_id,
            )
            return [MessageTriggerConfig(**dict(row)) for row in rows]

    async def upsert(
        self,
        channel_id: str,
        trigger_name: str,
        *,
        match_type: str | None = None,
        pattern: str | None = None,
        case_sensitive: bool | None = None,
        response: str | None = None,
        min_role: str | None = None,
        cooldown: int | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
    ) -> MessageTriggerConfig:
        """Insert or update a trigger. Invalidates list cache."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO message_triggers
                    (channel_id, trigger_name, match_type, pattern, case_sensitive,
                     response, min_role, cooldown, priority, enabled)
                VALUES
                    ($1, $2,
                     COALESCE($3, 'contains'), COALESCE($4, ''), COALESCE($5, FALSE),
                     COALESCE($6, ''), COALESCE($7, 'everyone'), $8,
                     COALESCE($9, 0), COALESCE($10, TRUE))
                ON CONFLICT (channel_id, trigger_name) DO UPDATE SET
                    match_type     = COALESCE($3, message_triggers.match_type),
                    pattern        = COALESCE($4, message_triggers.pattern),
                    case_sensitive = COALESCE($5, message_triggers.case_sensitive),
                    response       = COALESCE($6, message_triggers.response),
                    min_role       = COALESCE($7, message_triggers.min_role),
                    cooldown       = COALESCE($8, message_triggers.cooldown),
                    priority       = COALESCE($9, message_triggers.priority),
                    enabled        = COALESCE($10, message_triggers.enabled)
                RETURNING {_COLUMNS}
                """,
                channel_id,
                trigger_name,
                match_type,
                pattern,
                case_sensitive,
                response,
                min_role,
                cooldown,
                priority,
                enabled,
            )
            result = MessageTriggerConfig(**dict(row))
            _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
            return result

    async def delete(self, channel_id: str, trigger_name: str) -> bool:
        """Delete a trigger. Returns True if deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM message_triggers WHERE channel_id = $1 AND trigger_name = $2",
                channel_id,
                trigger_name,
            )
            _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
            return result == "DELETE 1"

    def invalidate_cache(self, channel_id: str) -> None:
        """Invalidate list cache for a channel (called by pg_notify handler)."""
        _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
