"""Repository for event_configs table."""

from __future__ import annotations

import json
import logging

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.event_config import EventConfig

logger = logging.getLogger(__name__)

# In-process cache for bot-side lookups — long TTL for memory-first reads.
_config_cache = AsyncTTLCache(maxsize=64, ttl=3600)
_config_list_cache = AsyncTTLCache(maxsize=16, ttl=3600)
_seeded_events: set[str] = set()

# Default templates per event type
DEFAULT_TEMPLATES: dict[str, str] = {
    "follow": "感謝 $(user) 的追隨！",
    "subscribe": "感謝 $(user) 的訂閱！",
    "raid": "$(user) 帶了 $(count) 個新朋友降落！",
}

# Default options per event type (only event types with options need entries)
DEFAULT_OPTIONS: dict[str, dict] = {
    "raid": {"auto_shoutout": True},
}

EVENT_TYPES = list(DEFAULT_TEMPLATES.keys())

_SELECT_COLS = (
    "id, channel_id, event_type, message_template, enabled, "
    "COALESCE(options, '{}') AS options, created_at, updated_at"
)


def _row_to_config(row: asyncpg.Record) -> EventConfig:
    """Convert a DB row to EventConfig, parsing options JSON string if needed."""
    d = dict(row)
    opts = d.get("options")
    if isinstance(opts, str):
        d["options"] = json.loads(opts)
    elif opts is None:
        d["options"] = {}
    return EventConfig(**d)


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
                f"SELECT {_SELECT_COLS} "
                "FROM event_configs WHERE channel_id = $1 AND event_type = $2",
                channel_id,
                event_type,
            )
            if not row:
                return None
            return _row_to_config(row)

    @cached(
        cache=_config_list_cache,
        key_func=lambda self, channel_id: f"event_list:{channel_id}",
    )
    async def list_configs(self, channel_id: str) -> list[EventConfig]:
        """Get all event configs for a channel."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SELECT_COLS} FROM event_configs WHERE channel_id = $1 ORDER BY id",
                channel_id,
            )
            return [_row_to_config(r) for r in rows]

    async def upsert_config(
        self,
        channel_id: str,
        event_type: str,
        message_template: str,
        enabled: bool,
        options: dict | None = None,
    ) -> EventConfig:
        """Insert or update an event config. Invalidates cache."""
        opts_json = json.dumps(options or {})
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO event_configs (channel_id, event_type, message_template, enabled, options)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (channel_id, event_type) DO UPDATE SET
                    message_template = EXCLUDED.message_template,
                    enabled = EXCLUDED.enabled,
                    options = EXCLUDED.options
                RETURNING {_SELECT_COLS}
                """,
                channel_id,
                event_type,
                message_template,
                enabled,
                opts_json,
            )
            result = _row_to_config(row)
            _config_cache.invalidate(f"event_config:{channel_id}:{event_type}")
            _config_list_cache.invalidate(f"event_list:{channel_id}")
            return result

    async def ensure_defaults(self, channel_id: str) -> list[EventConfig]:
        """Ensure default configs exist for a channel, then return all configs."""
        if channel_id not in _seeded_events:
            async with self.pool.acquire() as conn:
                for event_type, template in DEFAULT_TEMPLATES.items():
                    opts_json = json.dumps(DEFAULT_OPTIONS.get(event_type, {}))
                    await conn.execute(
                        """
                        INSERT INTO event_configs (channel_id, event_type, message_template, enabled, options)
                        VALUES ($1, $2, $3, TRUE, $4::jsonb)
                        ON CONFLICT (channel_id, event_type) DO NOTHING
                        """,
                        channel_id,
                        event_type,
                        template,
                        opts_json,
                    )
            _seeded_events.add(channel_id)
        return await self.list_configs(channel_id)
