"""Repository for command_configs and redemption_configs tables."""

from __future__ import annotations

import asyncio
import dataclasses
import logging

import asyncpg

from shared.builtin_commands import BUILTIN_ALIAS_MAP, BUILTIN_DEFS, BUILTIN_MAP
from shared.cache import AsyncTTLCache, cached
from shared.models.command_config import CommandConfig, RedemptionConfig

LOGGER: logging.Logger = logging.getLogger(__name__)

# In-process caches — long TTL for memory-first reads.
# Freshness is maintained by pg_notify (instant) + periodic refresh (5 min safety net).
_cmd_cache = AsyncTTLCache(maxsize=128, ttl=3600)
_cmd_list_cache = AsyncTTLCache(maxsize=32, ttl=3600)
_redemption_cache = AsyncTTLCache(maxsize=64, ttl=3600)

# Base columns without aliases (used in RETURNING / simple fetches before alias join)
_CMD_COLUMNS_BASE = (
    "id, channel_id, command_name, command_type, enabled, "
    "custom_response, cooldown, "
    "min_role, usage_count, created_at, updated_at"
)

# Full SELECT with aliases aggregated from command_aliases table
_CMD_SELECT = """
    SELECT cc.id, cc.channel_id, cc.command_name, cc.command_type, cc.enabled,
           cc.custom_response, cc.cooldown, cc.min_role,
           string_agg(ca.alias, ',' ORDER BY ca.alias) AS aliases,
           cc.usage_count, cc.created_at, cc.updated_at
    FROM command_configs cc
    LEFT JOIN command_aliases ca ON ca.command_id = cc.id"""

# Default redemption actions: (action_type, reward_name)
DEFAULT_REDEMPTIONS: list[dict] = [
    {"action_type": "vip", "reward_name": "vip"},
    {"action_type": "first", "reward_name": "1"},
    {"action_type": "niibot_auth", "reward_name": "niibot"},
    {"action_type": "game_queue", "reward_name": "game queue"},
    {"action_type": "video_queue", "reward_name": "video queue"},
]

type UnsetType = object
_UNSET: UnsetType = object()

# Track channels that already have redemption defaults seeded (avoids redundant INSERTs)
_seeded_redemptions: set[str] = set()


def _make_virtual(channel_id: str, defn: dict) -> CommandConfig:
    """Return a default CommandConfig for a builtin that has no DB row yet.

    Virtual configs have id=None and reflect the hardcoded defaults in
    shared.builtin_commands.BUILTIN_DEFS. They are stored in cache exactly
    like real DB rows and are replaced by real rows as soon as the user
    writes any override (toggle, cooldown change, etc.).
    """
    return CommandConfig(
        id=None,
        channel_id=channel_id,
        command_name=defn["command_name"],
        command_type="builtin",
        enabled=defn.get("enabled", True),
        custom_response=defn.get("custom_response"),
        cooldown=defn.get("cooldown"),
        min_role="everyone",
        aliases=defn.get("aliases"),
        usage_count=0,
        created_at=None,
        updated_at=None,
    )


def _fill_builtin_aliases(cfg: CommandConfig) -> CommandConfig:
    """Fill missing aliases on a builtin DB row from BUILTIN_MAP defaults.

    DB rows created by usage tracking (increment_usage_count) never write to
    command_aliases, so the LEFT JOIN returns NULL for aliases. Rather than
    showing no aliases in the UI, we fall back to the hardcoded defaults.
    """
    if cfg.command_type == "builtin" and cfg.aliases is None and cfg.command_name in BUILTIN_MAP:
        default_aliases = BUILTIN_MAP[cfg.command_name].get("aliases")
        if default_aliases:
            return dataclasses.replace(cfg, aliases=default_aliases)
    return cfg


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
                LOGGER.warning(
                    f"DB operation attempt {attempt}/{max_retries} failed: {type(e).__name__}, "
                    f"retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                LOGGER.exception(f"DB operation failed after {max_retries} attempts")
                raise


class CommandConfigRepository:
    """Pure SQL operations for command_configs.

    Builtin commands use a merge model: the DB only stores per-channel overrides
    (enabled state, custom_response, cooldown). When no DB row exists for a
    builtin, a virtual default is returned instead. This means new builtin
    commands defined in shared.builtin_commands automatically appear for every
    channel without any migration or seeding.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_cmd_cache,
        key_func=lambda self, channel_id, command_name: f"cmd_config:{channel_id}:{command_name}",
    )
    async def get_config(self, channel_id: str, command_name: str) -> CommandConfig | None:
        """Get a single command config by exact name (with cache).

        Returns the DB row if it exists (user has overrides), otherwise falls
        back to the virtual default for known builtins. Used by the bot at
        command execution time.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"{_CMD_SELECT} WHERE cc.channel_id = $1 AND cc.command_name = $2 GROUP BY cc.id",
                channel_id,
                command_name,
            )
            if row:
                return _fill_builtin_aliases(CommandConfig(**dict(row)))

        # Virtual fallback for builtins not yet overridden in DB
        if command_name in BUILTIN_MAP:
            return _make_virtual(channel_id, BUILTIN_MAP[command_name])
        return None

    async def find_by_name_or_alias(self, channel_id: str, name: str) -> CommandConfig | None:
        """Find a command config by command_name OR by alias match.

        Checks exact command_name first, then searches command_aliases table.
        Used by custom command handler in event_message.
        """
        # Try exact name first (uses cache + virtual fallback)
        config = await self.get_config(channel_id, name)
        if config:
            return config

        # Search by alias (also cached with virtual fallback)
        return await self._find_by_alias(channel_id, name)

    @cached(
        cache=_cmd_cache,
        key_func=lambda self, channel_id, name: f"cmd_alias:{channel_id}:{name}",
    )
    async def _find_by_alias(self, channel_id: str, name: str) -> CommandConfig | None:
        """Search for a command config by alias via command_aliases table."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"{_CMD_SELECT} "
                "WHERE cc.channel_id = $1 "
                "AND cc.id IN (SELECT command_id FROM command_aliases WHERE alias = $2) "
                "GROUP BY cc.id",
                channel_id,
                name,
            )
            if row:
                return CommandConfig(**dict(row))

        # Virtual builtin alias fallback: use get_config so DB override is respected
        if name in BUILTIN_ALIAS_MAP:
            cmd_name = BUILTIN_ALIAS_MAP[name]
            return await self.get_config(channel_id, cmd_name)
        return None

    @cached(
        cache=_cmd_list_cache,
        key_func=lambda self, channel_id: f"cmd_list:{channel_id}",
    )
    async def list_configs(self, channel_id: str) -> list[CommandConfig]:
        """Get all command configs for a channel.

        Merges builtin defaults (from BUILTIN_DEFS) with DB rows:
        - Builtins: DB row if the user has any override, otherwise virtual default.
        - Custom commands: always from DB.

        Order: builtins in BUILTIN_DEFS order, then custom commands.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"{_CMD_SELECT} WHERE cc.channel_id = $1 GROUP BY cc.id",
                channel_id,
            )

        db_rows: dict[str, CommandConfig] = {
            r["command_name"]: CommandConfig(**dict(r)) for r in rows
        }

        result: list[CommandConfig] = []

        # Builtins: respect DB override or fall back to virtual default
        for defn in BUILTIN_DEFS:
            name = defn["command_name"]
            if name in db_rows:
                result.append(_fill_builtin_aliases(db_rows[name]))
            else:
                result.append(_make_virtual(channel_id, defn))

        # Custom commands (only from DB, ordered by name)
        for row in sorted(db_rows.values(), key=lambda r: r.command_name):
            if row.command_type == "custom":
                result.append(row)

        return result

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
        """Insert or update a command config. Manages aliases in command_aliases table."""
        cd_value = None if cooldown is _UNSET else cooldown
        cd_provided = cooldown is not _UNSET
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []

        async def _query():
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        f"""
                        INSERT INTO command_configs
                            (channel_id, command_name, command_type, enabled,
                             custom_response, cooldown, min_role)
                        VALUES ($1, $2, $3,
                                COALESCE($4, TRUE), $5,
                                $6,
                                COALESCE($7, 'everyone'))
                        ON CONFLICT (channel_id, command_name) DO UPDATE SET
                            enabled = COALESCE($4, command_configs.enabled),
                            custom_response = COALESCE($5, command_configs.custom_response),
                            cooldown = CASE WHEN $8 THEN $6 ELSE command_configs.cooldown END,
                            min_role = COALESCE($7, command_configs.min_role)
                        RETURNING {_CMD_COLUMNS_BASE}
                        """,
                        channel_id,
                        command_name,
                        command_type,
                        enabled,
                        custom_response,
                        cd_value,
                        min_role,
                        cd_provided,
                    )
                    cmd_id = row["id"]

                    # Replace aliases only when aliases argument was explicitly provided
                    if aliases is not None:
                        await conn.execute(
                            "DELETE FROM command_aliases WHERE command_id = $1", cmd_id
                        )
                        for alias in alias_list:
                            await conn.execute(
                                "INSERT INTO command_aliases (command_id, alias) VALUES ($1, $2) "
                                "ON CONFLICT DO NOTHING",
                                cmd_id,
                                alias,
                            )

                    # Fetch with aggregated aliases
                    result_row = await conn.fetchrow(
                        f"{_CMD_SELECT} WHERE cc.id = $1 GROUP BY cc.id",
                        cmd_id,
                    )
                    result = CommandConfig(**dict(result_row))

                # Invalidate name cache
                _cmd_cache.invalidate(f"cmd_config:{channel_id}:{command_name}")
                _cmd_list_cache.invalidate(f"cmd_list:{channel_id}")

                # Invalidate alias caches — explicit aliases passed + builtin default aliases
                aliases_to_invalidate: set[str] = set(alias_list)
                if command_name in BUILTIN_MAP:
                    for a in (BUILTIN_MAP[command_name].get("aliases") or "").split(","):
                        a = a.strip()
                        if a:
                            aliases_to_invalidate.add(a)
                for alias in aliases_to_invalidate:
                    _cmd_cache.invalidate(f"cmd_alias:{channel_id}:{alias}")

                return result

        return await _retry_on_db_error(_query)

    async def increment_usage_count(self, channel_id: str, command_name: str) -> None:
        """Increment usage_count for a command by 1 and record last_used_at.

        For virtual builtins (no DB row), this also creates the row so that
        usage tracking works correctly.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO command_configs
                    (channel_id, command_name, command_type, enabled, usage_count, last_used_at)
                VALUES ($1, $2, 'builtin', TRUE, 1, NOW())
                ON CONFLICT (channel_id, command_name) DO UPDATE SET
                    usage_count = command_configs.usage_count + 1,
                    last_used_at = NOW()
                """,
                channel_id,
                command_name,
            )
        # Invalidate the name cache so the updated usage_count is reflected
        _cmd_cache.invalidate(f"cmd_config:{channel_id}:{command_name}")
        _cmd_list_cache.invalidate(f"cmd_list:{channel_id}")

    async def delete_config(self, channel_id: str, command_name: str) -> bool:
        """Delete a command config (custom commands only). Returns True if deleted.

        command_aliases rows are removed automatically via ON DELETE CASCADE.
        """
        # Get config first for alias cache invalidation
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

    async def warm_cache(self, channel_id: str) -> int:
        """Proactively load all command configs for a channel into the in-memory cache.

        Populates both exact-name keys and alias keys (including virtual builtins)
        so that runtime lookups are O(1) memory access with zero DB dependency.

        Returns the number of configs warmed.
        """
        configs = await self.list_configs(channel_id)
        for cfg in configs:
            _cmd_cache.set(f"cmd_config:{channel_id}:{cfg.command_name}", cfg)
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

    def invalidate_channel(self, channel_id: str) -> None:
        """Invalidate all cached redemptions for a single channel."""
        _redemption_cache.invalidate_prefix(f"redemption:{channel_id}:")

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
                if config.reward_name and config.reward_name.lower() in reward_lower:
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
