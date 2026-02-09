"""Repository for command_configs and redemption_configs tables."""

from __future__ import annotations

import logging
from typing import TypeAlias

import asyncpg

from shared.cache import _MISSING, AsyncTTLCache
from shared.models.command_config import CommandConfig, RedemptionConfig

logger = logging.getLogger(__name__)

# In-process caches
_cmd_cache = AsyncTTLCache(maxsize=128, ttl=60)
_redemption_cache = AsyncTTLCache(maxsize=64, ttl=60)

_CMD_COLUMNS = (
    "id, channel_id, command_name, command_type, enabled, "
    "custom_response, cooldown, "
    "min_role, aliases, created_at, updated_at"
)

# Default builtin commands: cooldown values are overrides (None = use channel default)
BUILTIN_COMMANDS: list[dict] = [
    {"command_name": "hi", "custom_response": "你好，$(user)！", "cooldown": 5},
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
]

UnsetType: TypeAlias = object
_UNSET: UnsetType = object()


class CommandConfigRepository:
    """Pure SQL operations for command_configs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_config(self, channel_id: str, command_name: str) -> CommandConfig | None:
        """Get a single command config by exact name (with cache). Used by the bot at command time."""
        cache_key = f"cmd_config:{channel_id}:{command_name}"
        cached = _cmd_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_CMD_COLUMNS} "
                "FROM command_configs WHERE channel_id = $1 AND command_name = $2",
                channel_id,
                command_name,
            )
            if not row:
                _cmd_cache.set(cache_key, None)
                return None
            result = CommandConfig(**dict(row))
            _cmd_cache.set(cache_key, result)
            return result

    async def find_by_name_or_alias(self, channel_id: str, name: str) -> CommandConfig | None:
        """Find a command config by command_name OR by alias match.

        Checks exact command_name first, then searches aliases (comma-separated).
        Used by custom command handler in event_message.
        """
        # Try exact name first (uses cache)
        config = await self.get_config(channel_id, name)
        if config:
            return config

        # Search by alias
        cache_key = f"cmd_alias:{channel_id}:{name}"
        cached = _cmd_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

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
                _cmd_cache.set(cache_key, None)
                return None
            result = CommandConfig(**dict(row))
            _cmd_cache.set(cache_key, result)
            return result

    async def list_configs(self, channel_id: str) -> list[CommandConfig]:
        """Get all command configs for a channel."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_CMD_COLUMNS} FROM command_configs WHERE channel_id = $1 ORDER BY id",
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
        """Insert or update a command config. Invalidates cache.

        Cooldown uses a sentinel to distinguish "not provided" (keep existing)
        from explicit None (use channel default) or int (override).
        """
        cd_value = None if cooldown is _UNSET else cooldown
        cd_provided = cooldown is not _UNSET

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
            # Invalidate both name and alias caches
            _cmd_cache.invalidate(f"cmd_config:{channel_id}:{command_name}")
            if aliases:
                for alias in aliases.split(","):
                    _cmd_cache.invalidate(f"cmd_alias:{channel_id}:{alias.strip()}")
            return result

    async def delete_config(self, channel_id: str, command_name: str) -> bool:
        """Delete a command config (custom commands only). Returns True if deleted."""
        # Get config first for cache invalidation
        config = await self.get_config(channel_id, command_name)
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM command_configs "
                "WHERE channel_id = $1 AND command_name = $2 AND command_type = 'custom'",
                channel_id,
                command_name,
            )
            _cmd_cache.invalidate(f"cmd_config:{channel_id}:{command_name}")
            if config and config.aliases:
                for alias in config.aliases.split(","):
                    _cmd_cache.invalidate(f"cmd_alias:{channel_id}:{alias.strip()}")
            return result == "DELETE 1"

    async def ensure_defaults(self, channel_id: str) -> list[CommandConfig]:
        """Ensure default builtin commands exist for a channel, then return all configs."""
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
                    cmd.get("cooldown"),  # None = use channel default
                )
        return await self.list_configs(channel_id)


class RedemptionConfigRepository:
    """Pure SQL operations for redemption_configs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_configs(self, channel_id: str) -> list[RedemptionConfig]:
        """Get all redemption configs for a channel."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, channel_id, action_type, reward_name, enabled, "
                "created_at, updated_at "
                "FROM redemption_configs WHERE channel_id = $1 ORDER BY id",
                channel_id,
            )
            return [RedemptionConfig(**dict(row)) for row in rows]

    async def find_by_reward_name(
        self, channel_id: str, reward_name: str
    ) -> RedemptionConfig | None:
        """Find a redemption config by reward name (case-insensitive contains). Bot use."""
        cache_key = f"redemption:{channel_id}:{reward_name.lower()}"
        cached = _redemption_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

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
                    _redemption_cache.set(cache_key, config)
                    return config

            _redemption_cache.set(cache_key, None)
            return None

    async def upsert_config(
        self,
        channel_id: str,
        action_type: str,
        reward_name: str,
        enabled: bool = True,
    ) -> RedemptionConfig:
        """Insert or update a redemption config. Invalidates cache."""
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

    async def ensure_defaults(self, channel_id: str) -> list[RedemptionConfig]:
        """Ensure default redemption configs exist for a channel."""
        async with self.pool.acquire() as conn:
            for r in DEFAULT_REDEMPTIONS:
                await conn.execute(
                    """
                    INSERT INTO redemption_configs (channel_id, action_type, reward_name, enabled)
                    VALUES ($1, $2, $3, TRUE)
                    ON CONFLICT (channel_id, action_type) DO NOTHING
                    """,
                    channel_id,
                    r["action_type"],
                    r["reward_name"],
                )
        return await self.list_configs(channel_id)
