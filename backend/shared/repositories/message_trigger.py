"""Repository for message_triggers table."""

from __future__ import annotations

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.message_trigger import MessageTriggerConfig

_trigger_list_cache = AsyncTTLCache(maxsize=32, ttl=3600, name="message_trigger.trigger_list")

_COLUMNS_BASE = (
    "id, channel_id, trigger_name, match_type, pattern, case_sensitive, "
    "response, min_role, cooldown, priority, enabled, usage_count, created_at, updated_at"
)

# Full SELECT with aliases aggregated from trigger_aliases table
_TRIGGER_SELECT = """
    SELECT mt.id, mt.channel_id, mt.trigger_name, mt.match_type, mt.pattern,
           mt.case_sensitive, mt.response, mt.min_role, mt.cooldown, mt.priority,
           mt.enabled, mt.usage_count,
           string_agg(ta.alias, ',' ORDER BY ta.alias) AS aliases,
           mt.created_at, mt.updated_at
    FROM message_triggers mt
    LEFT JOIN trigger_aliases ta ON ta.trigger_id = mt.id"""


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
                f"{_TRIGGER_SELECT} "
                "WHERE mt.channel_id = $1 AND mt.enabled = TRUE "
                "GROUP BY mt.id "
                "ORDER BY mt.priority DESC, mt.id",
                channel_id,
            )
            return [MessageTriggerConfig(**dict(row)) for row in rows]

    async def get_by_name(self, channel_id: str, trigger_name: str) -> MessageTriggerConfig | None:
        """Fetch a single trigger by channel_id + trigger_name."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"{_TRIGGER_SELECT} "
                "WHERE mt.channel_id = $1 AND mt.trigger_name = $2 "
                "GROUP BY mt.id",
                channel_id,
                trigger_name,
            )
            return MessageTriggerConfig(**dict(row)) if row else None

    async def list_all(self, channel_id: str) -> list[MessageTriggerConfig]:
        """Return all triggers for a channel (enabled + disabled)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"{_TRIGGER_SELECT} "
                "WHERE mt.channel_id = $1 "
                "GROUP BY mt.id "
                "ORDER BY mt.priority DESC, mt.id",
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
        aliases: str | None = None,
    ) -> MessageTriggerConfig:
        """Insert or update a trigger. Manages aliases in trigger_aliases table."""
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO message_triggers
                        (channel_id, trigger_name, match_type, pattern, case_sensitive,
                         response, min_role, cooldown, priority, enabled)
                    VALUES
                        ($1, $2,
                         COALESCE($3, 'startswith'), COALESCE($4, ''), COALESCE($5, FALSE),
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
                    RETURNING {_COLUMNS_BASE}
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
                trigger_id = row["id"]

                # Replace aliases only when aliases argument was explicitly provided
                if aliases is not None:
                    await conn.execute(
                        "DELETE FROM trigger_aliases WHERE trigger_id = $1", trigger_id
                    )
                    for alias in alias_list:
                        await conn.execute(
                            "INSERT INTO trigger_aliases (trigger_id, alias) VALUES ($1, $2) "
                            "ON CONFLICT DO NOTHING",
                            trigger_id,
                            alias,
                        )

                # Fetch with aggregated aliases
                result_row = await conn.fetchrow(
                    f"{_TRIGGER_SELECT} WHERE mt.id = $1 GROUP BY mt.id",
                    trigger_id,
                )
                result = MessageTriggerConfig(**dict(result_row))

            _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
            return result

    async def try_insert(
        self,
        channel_id: str,
        trigger_name: str,
        *,
        match_type: str,
        pattern: str,
        case_sensitive: bool,
        response: str,
        min_role: str,
        cooldown: int | None,
        priority: int,
        enabled: bool,
        aliases: str | None = None,
    ) -> MessageTriggerConfig | None:
        """Atomically create a brand-new trigger; returns None if the name is taken.

        Unlike upsert (always succeeds via ON CONFLICT DO UPDATE), this relies
        on the DB's unique constraint on (channel_id, trigger_name) so a
        check-then-insert race between two concurrent callers can't silently
        overwrite one caller's trigger with the other's.
        """
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO message_triggers
                        (channel_id, trigger_name, match_type, pattern, case_sensitive,
                         response, min_role, cooldown, priority, enabled)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (channel_id, trigger_name) DO NOTHING
                    RETURNING {_COLUMNS_BASE}
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
                if row is None:
                    return None
                for alias in alias_list:
                    await conn.execute(
                        "INSERT INTO trigger_aliases (trigger_id, alias) VALUES ($1, $2) "
                        "ON CONFLICT DO NOTHING",
                        row["id"],
                        alias,
                    )
                result = MessageTriggerConfig(**dict(row))
                if alias_list:
                    result.aliases = ",".join(sorted(alias_list))

            _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
            return result

    async def delete(self, channel_id: str, trigger_name: str) -> bool:
        """Delete a trigger. Returns True if deleted.

        trigger_aliases rows are removed automatically via ON DELETE CASCADE.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM message_triggers WHERE channel_id = $1 AND trigger_name = $2",
                channel_id,
                trigger_name,
            )
            _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
            return result == "DELETE 1"

    async def increment_usage_count(self, trigger_id: int) -> None:
        """Increment usage_count for a trigger by ID. Does not invalidate list cache."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE message_triggers SET usage_count = usage_count + 1 WHERE id = $1",
                trigger_id,
            )

    def invalidate_cache(self, channel_id: str) -> None:
        """Invalidate list cache for a channel (called by pg_notify handler)."""
        _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")
