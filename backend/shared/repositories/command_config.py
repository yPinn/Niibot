"""Repository for command_configs and redemption_configs tables."""

from __future__ import annotations

import asyncio
import logging
from typing import TypeAlias

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.command_config import CommandConfig, RedemptionConfig

logger = logging.getLogger(__name__)

# In-process caches — long TTL for memory-first reads.
# Freshness is maintained by pg_notify (instant) + periodic refresh (5 min safety net).
_cmd_cache = AsyncTTLCache(maxsize=128, ttl=3600)
_cmd_list_cache = AsyncTTLCache(maxsize=32, ttl=3600)
_redemption_cache = AsyncTTLCache(maxsize=64, ttl=3600)

_CMD_COLUMNS = (
    "id, channel_id, command_name, command_type, enabled, "
    "custom_response, cooldown, "
    "min_role, aliases, created_at, updated_at"
)

# Default builtin commands: cooldown values are overrides (None = use channel default)
BUILTIN_COMMANDS: list[dict] = [
    {"command_name": "hi", "custom_response": "你好,$(user)!", "cooldown": 5},
    {"command_name": "help", "cooldown": 5},
    {"command_name": "uptime", "cooldown": 5},
    {"command_name": "ai", "cooldown": 15},
    {"command_name": "運勢", "cooldown": 5},
    {"command_name": "rk", "cooldown": 5},
]

# Default redemption actions: (action_type, reward_name)
DEFAULT_REDEMPTIONS: list[dict] = [
    {"action_type": "vip", "reward_name": "vip"},
    {"action_type": "first", "reward_name": "1"},
    {"action_type": "niibot_auth", "reward_name": "niibot"},
    {"action_type": "game_queue", "reward_name": "game queue"},
]

UnsetType: TypeAlias = object
_UNSET: UnsetType = object()

# Track channels that already have defaults seeded (avoids redundant INSERTs)
_seeded_channels: set[str] = set()
_seeded_redemptions: set[str] = set()


async def _retry_on_db_error(func, max_retries: int = 2):
    """Retry helper for write operations."""
    for attempt in range(1, max_retries + 1):
        try:
            return await func()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if attempt < max_retries:
                delay = 0.5 * attempt
                logger.warning(
                    f"DB operation attempt {attempt}/{max_retries} failed: {type(e).__name__}, "
                    f"retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.exception(f"DB operation failed after {max_retries} attempts")
                raise


class CommandConfigRepository:
    """Pure SQL operations for command_configs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_cmd_cache,
        key_func=lambda self, channel_id, command_name: f"cmd_config:{channel_id}:{command_name}",
    )
    async def get_config(self, channel_id: str, command_name: str) -> CommandConfig | None:
        """Get a single command config by exact name (with cache). Used by the bot at command time."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_CMD_COLUMNS} "
                "FROM command_configs WHERE channel_id = $1 AND command_name = $2",
                channel_id,
                command_name,
            )
            if not row:
                return None
            return CommandConfig(**dict(row))

    async def find_by_name_or_alias(self, channel_id: str, name: str) -> CommandConfig | None:
        """Find a command config by command_name OR by alias match.

        Checks exact command_name first, then searches aliases (comma-separated).
        Used by custom command handler in event_message.
        """
        # Try exact name first (uses cache)
        config = await self.get_config(channel_id, name)
        if config:
            return config

        # Search by alias (also cached with resilience)
        return await self._find_by_alias(channel_id, name)

    @cached(
        cache=_cmd_cache,
        key_func=lambda self, channel_id, name: f"cmd_alias:{channel_id}:{name}",
    )
    async def _find_by_alias(self, channel_id: str, name: str) -> CommandConfig | None:
        """Search for a command config by alias."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_CMD_COLUMNS} "
                "FROM command_configs "
                "WHERE channel_id = $1 AND aliases IS NOT NULL "
                "AND $2 = ANY(string_to_array(aliases, ','))",
                channel_id,
                name,
            )
            if not row:
                return None
            return CommandConfig(**dict(row))

    @cached(
        cache=_cmd_list_cache,
        key_func=lambda self, channel_id: f"cmd_list:{channel_id}",
    )
    async def list_configs(self, channel_id: str) -> list[CommandConfig]:
        """Get all command configs for a channel."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_CMD_COLUMNS} FROM command_configs WHERE channel_id = $1 ORDER BY command_type, command_name",
                channel_id,
            )
            return [CommandConfig(**dict(row)) for row in rows]

    async def upsert_config(
        self,
        channel_id: str,
        command_name: str,
        *,
        command_type: str = "builtin",
        enabled: bool | None = None,
        custom_response: str | None = None,
        cooldown: int | None | UnsetType = _UNSET,
        min_role: str | None = None,
        aliases: str | None = None,
    ) -> CommandConfig:
        """Insert or update a command config. Invalidates cache."""
        cd_value = None if cooldown is _UNSET else cooldown
        cd_provided = cooldown is not _UNSET

        async def _query():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO command_configs
                        (channel_id, command_name, command_type, enabled,
                         custom_response, cooldown,
                         min_role, aliases)
                    VALUES ($1, $2, $3,
                            COALESCE($4, TRUE), $5,
                            $6,
                            COALESCE($7, 'everyone'), $8)
                    ON CONFLICT (channel_id, command_name) DO UPDATE SET
                        enabled = COALESCE($4, command_configs.enabled),
                        custom_response = COALESCE($5, command_configs.custom_response),
                        cooldown = CASE WHEN $9 THEN $6 ELSE command_configs.cooldown END,
                        min_role = COALESCE($7, command_configs.min_role),
                        aliases = COALESCE($8, command_configs.aliases)
                    RETURNING {_CMD_COLUMNS}
                    """,
                    channel_id,
                    command_name,
                    command_type,
                    enabled,
                    custom_response,
                    cd_value,
                    min_role,
                    aliases,
                    cd_provided,
                )
                result = CommandConfig(**dict(row))
                # Invalidate name, alias, and list caches
                _cmd_cache.invalidate(f"cmd_config:{channel_id}:{command_name}")
                _cmd_list_cache.invalidate(f"cmd_list:{channel_id}")
                if aliases:
                    for alias in aliases.split(","):
                        _cmd_cache.invalidate(f"cmd_alias:{channel_id}:{alias.strip()}")
                return result

        return await _retry_on_db_error(_query)

    async def delete_config(self, channel_id: str, command_name: str) -> bool:
        """Delete a command config (custom commands only). Returns True if deleted."""
        # Get config first for cache invalidation
        config = await self.get_config(channel_id, command_name)

        async def _query():
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM command_configs "
                    "WHERE channel_id = $1 AND command_name = $2 AND command_type = 'custom'",
                    channel_id,
                    command_name,
                )
                _cmd_cache.invalidate(f"cmd_config:{channel_id}:{command_name}")
                _cmd_list_cache.invalidate(f"cmd_list:{channel_id}")
                if config and config.aliases:
                    for alias in config.aliases.split(","):
                        _cmd_cache.invalidate(f"cmd_alias:{channel_id}:{alias.strip()}")
                return result == "DELETE 1"

        return await _retry_on_db_error(_query)

    async def ensure_defaults(self, channel_id: str) -> list[CommandConfig]:
        """Ensure default builtin commands exist for a channel, then return all configs."""
        if channel_id not in _seeded_channels:

            async def _query():
                async with self.pool.acquire() as conn:
                    for cmd in BUILTIN_COMMANDS:
                        await conn.execute(
                            """
                            INSERT INTO command_configs
                                (channel_id, command_name, command_type, enabled,
                                 custom_response, cooldown)
                            VALUES ($1, $2, 'builtin', TRUE, $3, $4)
                            ON CONFLICT (channel_id, command_name) DO NOTHING
                            """,
                            channel_id,
                            cmd["command_name"],
                            cmd.get("custom_response"),
                            cmd.get("cooldown"),
                        )

            await _retry_on_db_error(_query)
            _seeded_channels.add(channel_id)

        return await self.list_configs(channel_id)

    async def warm_cache(self, channel_id: str) -> int:
        """Proactively load all command configs for a channel into the in-memory cache.

        Populates both exact-name keys and alias keys so that runtime lookups
        are O(1) memory access with zero DB dependency.

        Returns the number of configs warmed.
        """
        configs = await self.list_configs(channel_id)
        for cfg in configs:
            # Populate exact name cache
            _cmd_cache.set(f"cmd_config:{channel_id}:{cfg.command_name}", cfg)
            # Populate alias cache entries
            if cfg.aliases:
                for alias in cfg.aliases.split(","):
                    alias = alias.strip()
                    if alias:
                        _cmd_cache.set(f"cmd_alias:{channel_id}:{alias}", cfg)
        return len(configs)


class RedemptionConfigRepository:
    """Pure SQL operations for redemption_configs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_configs(self, channel_id: str) -> list[RedemptionConfig]:
        """Get all redemption configs for a channel."""

        async def _query():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, channel_id, action_type, reward_name, enabled, "
                    "created_at, updated_at "
                    "FROM redemption_configs WHERE channel_id = $1 ORDER BY id",
                    channel_id,
                )
                return [RedemptionConfig(**dict(row)) for row in rows]

        return await _retry_on_db_error(_query)

    @cached(
        cache=_redemption_cache,
        key_func=lambda self, channel_id, reward_name: (
            f"redemption:{channel_id}:{reward_name.lower()}"
        ),
    )
    async def find_by_reward_name(
        self, channel_id: str, reward_name: str
    ) -> RedemptionConfig | None:
        """Find a redemption config by reward name (case-insensitive contains). Bot use."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, channel_id, action_type, reward_name, enabled, "
                "created_at, updated_at "
                "FROM redemption_configs WHERE channel_id = $1 AND enabled = TRUE",
                channel_id,
            )
            # Match: reward_name is contained in the reward title (case-insensitive)
            reward_lower = reward_name.lower()
            for row in rows:
                config = RedemptionConfig(**dict(row))
                if config.reward_name.lower() in reward_lower:
                    return config

            return None

    async def upsert_config(
        self,
        channel_id: str,
        action_type: str,
        reward_name: str,
        enabled: bool = True,
    ) -> RedemptionConfig:
        """Insert or update a redemption config. Invalidates cache."""

        async def _query():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO redemption_configs (channel_id, action_type, reward_name, enabled)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (channel_id, action_type) DO UPDATE SET
                        reward_name = EXCLUDED.reward_name,
                        enabled = EXCLUDED.enabled
                    RETURNING id, channel_id, action_type, reward_name, enabled,
                              created_at, updated_at
                    """,
                    channel_id,
                    action_type,
                    reward_name,
                    enabled,
                )
                result = RedemptionConfig(**dict(row))
                _redemption_cache.clear()
                return result

        return await _retry_on_db_error(_query)

    async def ensure_defaults(
        self, channel_id: str, *, owner_id: str | None = None
    ) -> list[RedemptionConfig]:
        """Ensure default redemption configs exist for a channel.

        ``niibot_auth`` is only seeded when *channel_id* matches *owner_id*.
        All defaults are created with ``enabled=FALSE`` so users opt-in explicitly.
        """
        if channel_id not in _seeded_redemptions:

            async def _query():
                async with self.pool.acquire() as conn:
                    for r in DEFAULT_REDEMPTIONS:
                        if r["action_type"] == "niibot_auth" and channel_id != owner_id:
                            continue
                        await conn.execute(
                            """
                            INSERT INTO redemption_configs (channel_id, action_type, reward_name, enabled)
                            VALUES ($1, $2, $3, FALSE)
                            ON CONFLICT (channel_id, action_type) DO NOTHING
                            """,
                            channel_id,
                            r["action_type"],
                            r["reward_name"],
                        )

            await _retry_on_db_error(_query)
            _seeded_redemptions.add(channel_id)

        return await self.list_configs(channel_id)
