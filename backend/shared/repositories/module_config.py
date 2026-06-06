"""Repository for global module configuration.

Stores system-wide settings (e.g. enabled knowledge packs) that apply uniformly
to all channels. Unlike ai_settings, these are NOT per-channel.
"""

from __future__ import annotations

import json
import logging

import asyncpg

from shared.cache import AsyncTTLCache, cached

LOGGER = logging.getLogger(__name__)

_module_config_cache = AsyncTTLCache(maxsize=16, ttl=300)

_ENABLED_PACKS_KEY = "enabled_packs"
_CACHE_KEY = f"module_config:{_ENABLED_PACKS_KEY}"


class ModuleConfigRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_module_config_cache,
        key_func=lambda self: _CACHE_KEY,
    )
    async def get_enabled_packs(self) -> list[str]:
        """Return globally enabled knowledge pack IDs."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM module_config WHERE key = $1",
                _ENABLED_PACKS_KEY,
            )
        if not row:
            return []
        return list(json.loads(row["value"]) or [])

    async def set_enabled_packs(self, pack_ids: list[str]) -> list[str]:
        """Persist globally enabled pack IDs and invalidate cache."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO module_config (key, value, updated_at)
                VALUES ($1, $2::jsonb, now())
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = now()
                """,
                _ENABLED_PACKS_KEY,
                json.dumps(pack_ids),
            )
        _module_config_cache.invalidate(_CACHE_KEY)
        LOGGER.info("Global enabled_packs updated: %s", pack_ids)
        return pack_ids
