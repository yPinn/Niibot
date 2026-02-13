"""Repository for event_configs table."""

from __future__ import annotations

import logging

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.event_config import EventConfig

logger = logging.getLogger(__name__)

# In-process cache for bot-side lookups
_config_cache = AsyncTTLCache(maxsize=64, ttl=60)
_config_list_cache = AsyncTTLCache(maxsize=16, ttl=30)
_seeded_events: set[str] = set()

# Default templates per event type
DEFAULT_TEMPLATES: dict[str, str] = {
    "follow": "感謝 $(user) 的追隨！",
    "subscribe": "感謝 $(user) 的訂閱！",
    "raid": "$(user) 帶了 $(count) 個新朋友降落！",
}

EVENT_TYPES = list(DEFAULT_TEMPLATES.keys())


class EventConfigRepository:
    """Pure SQL operations for event_configs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_config_cache,
        key_func=lambda self, channel_id, event_type: f"event_config:{channel_id}:{event_type}",
    )
    async def get_config(self, channel_id: str, event_type: str) -> EventConfig | None:
        """Get a single event config (with cache). Used by the bot at event time."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, channel_id, event_type, message_template, enabled, "
                "created_at, updated_at "
                "FROM event_configs WHERE channel_id = $1 AND event_type = $2",
                channel_id,
                event_type,
            )
            if not row:
                return None
            return EventConfig(**dict(row))

    @cached(
        cache=_config_list_cache,
        key_func=lambda self, channel_id: f"event_list:{channel_id}",
    )
    async def list_configs(self, channel_id: str) -> list[EventConfig]:
        """Get all event configs for a channel."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, channel_id, event_type, message_template, enabled, "
                "created_at, updated_at "
                "FROM event_configs WHERE channel_id = $1 ORDER BY id",
                channel_id,
            )
            return [EventConfig(**dict(r)) for r in rows]

    async def upsert_config(
        self,
        channel_id: str,
        event_type: str,
        message_template: str,
        enabled: bool,
    ) -> EventConfig:
        """Insert or update an event config. Invalidates cache."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO event_configs (channel_id, event_type, message_template, enabled)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (channel_id, event_type) DO UPDATE SET
                    message_template = EXCLUDED.message_template,
                    enabled = EXCLUDED.enabled
                RETURNING id, channel_id, event_type, message_template, enabled,
                          created_at, updated_at
                """,
                channel_id,
                event_type,
                message_template,
                enabled,
            )
            result = EventConfig(**dict(row))
            _config_cache.invalidate(f"event_config:{channel_id}:{event_type}")
            _config_list_cache.invalidate(f"event_list:{channel_id}")
            return result

    async def ensure_defaults(self, channel_id: str) -> list[EventConfig]:
        """Ensure default configs exist for a channel, then return all configs."""
        if channel_id not in _seeded_events:
            async with self.pool.acquire() as conn:
                for event_type, template in DEFAULT_TEMPLATES.items():
                    await conn.execute(
                        """
                        INSERT INTO event_configs (channel_id, event_type, message_template, enabled)
                        VALUES ($1, $2, $3, TRUE)
                        ON CONFLICT (channel_id, event_type) DO NOTHING
                        """,
                        channel_id,
                        event_type,
                        template,
                    )
            _seeded_events.add(channel_id)
        return await self.list_configs(channel_id)
