"""Repository for tokens, channels, and discord_users tables."""

from __future__ import annotations

import logging

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.channel import Channel, DiscordUser, Token

logger = logging.getLogger(__name__)

# --- In-process caches ---
# Long TTL for memory-first reads; freshness via pg_notify + periodic refresh.
_token_cache = AsyncTTLCache(maxsize=64, ttl=3600)
_channel_cache = AsyncTTLCache(maxsize=64, ttl=3600)
_enabled_channels_cache = AsyncTTLCache(maxsize=1, ttl=3600)
_discord_user_cache = AsyncTTLCache(maxsize=64, ttl=300)


class ChannelRepository:
    """Pure SQL operations for tokens / channels / discord_users."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ==================== Token Operations ====================

    @cached(cache=_token_cache, key_func=lambda self, user_id: f"token:{user_id}")
    async def get_token(self, user_id: str) -> Token | None:
        """Get a user's OAuth token."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, token, refresh, created_at, updated_at "
                "FROM tokens WHERE user_id = $1",
                user_id,
            )
            if not row:
                return None
            return Token(**dict(row))

    async def upsert_token_only(
        self,
        user_id: str,
        token: str,
        refresh: str,
    ) -> None:
        """Insert or update an OAuth token (without touching the channels table)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tokens (user_id, token, refresh)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    token      = EXCLUDED.token,
                    refresh    = EXCLUDED.refresh,
                    updated_at = NOW()
                """,
                user_id,
                token,
                refresh,
            )
        _token_cache.invalidate(f"token:{user_id}")

    async def list_tokens(self) -> list[Token]:
        """Return all tokens."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, token, refresh, created_at, updated_at FROM tokens"
            )
            return [Token(**dict(r)) for r in rows]

    async def upsert_token(
        self,
        user_id: str,
        token: str,
        refresh: str,
        channel_name: str = "",
    ) -> None:
        """Insert or update an OAuth token and ensure a channels row exists.

        This is a single transaction: tokens upsert + channels upsert.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO tokens (user_id, token, refresh)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET
                        token      = EXCLUDED.token,
                        refresh    = EXCLUDED.refresh,
                        updated_at = NOW()
                    """,
                    user_id,
                    token,
                    refresh,
                )
                await conn.execute(
                    """
                    INSERT INTO channels (channel_id, channel_name, enabled)
                    VALUES ($1, $2, TRUE)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        updated_at   = NOW()
                    """,
                    user_id,
                    channel_name,
                )

        _token_cache.invalidate(f"token:{user_id}")
        _channel_cache.invalidate(f"channel:{user_id}")
        _enabled_channels_cache.clear()

    # ==================== Channel Operations ====================

    @cached(cache=_channel_cache, key_func=lambda self, channel_id: f"channel:{channel_id}")
    async def get_channel(self, channel_id: str) -> Channel | None:
        """Get a single channel by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT channel_id, channel_name, enabled, default_cooldown,created_at, updated_at "
                "FROM channels WHERE channel_id = $1",
                channel_id,
            )
            if not row:
                return None
            return Channel(**dict(row))

    @cached(
        cache=_enabled_channels_cache,
        key_func=lambda self: "enabled_channels",
    )
    async def list_enabled_channels(self) -> list[Channel]:
        """Return all enabled channels."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT channel_id, channel_name, enabled, default_cooldown,created_at, updated_at "
                "FROM channels WHERE enabled = TRUE"
            )
            return [Channel(**dict(r)) for r in rows]

    def warm_channel_cache(self, channels: list[Channel]) -> int:
        """Populate the channel cache from an already-fetched list.

        Called at startup after list_enabled_channels() to ensure
        get_channel() has stale data for fallback during DB outages.
        """
        for ch in channels:
            _channel_cache.set(f"channel:{ch.channel_id}", ch)
        return len(channels)

    async def list_all_channels(self) -> list[Channel]:
        """Return all channels (including disabled)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT channel_id, channel_name, enabled, default_cooldown,created_at, updated_at FROM channels"
            )
            return [Channel(**dict(r)) for r in rows]

    async def upsert_channel(
        self, channel_id: str, channel_name: str, enabled: bool = True
    ) -> None:
        """Insert or update a channel row."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channels (channel_id, channel_name, enabled)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
                    enabled      = EXCLUDED.enabled,
                    updated_at   = NOW()
                """,
                channel_id,
                channel_name,
                enabled,
            )
        _channel_cache.invalidate(f"channel:{channel_id}")
        _enabled_channels_cache.clear()

    async def disable_channel_by_name(self, channel_name: str) -> None:
        """Disable a channel by its name."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE channels SET enabled = FALSE, updated_at = NOW() WHERE channel_name = $1",
                channel_name,
            )
        _enabled_channels_cache.clear()

    async def update_channel_enabled(self, channel_id: str, enabled: bool) -> None:
        """Toggle a channel's enabled state."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE channels SET enabled = $1, updated_at = NOW() WHERE channel_id = $2",
                enabled,
                channel_id,
            )
        _channel_cache.invalidate(f"channel:{channel_id}")
        _enabled_channels_cache.clear()

    async def list_empty_name_channels(self) -> list[Channel]:
        """Return channels whose channel_name is empty or NULL."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT channel_id, channel_name, enabled, default_cooldown,created_at, updated_at "
                "FROM channels WHERE channel_name IS NULL OR channel_name = ''"
            )
            return [Channel(**dict(r)) for r in rows]

    async def update_channel_name(self, channel_id: str, name: str) -> None:
        """Update a channel's display name."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE channels SET channel_name = $1, updated_at = NOW() WHERE channel_id = $2",
                name,
                channel_id,
            )
        _channel_cache.invalidate(f"channel:{channel_id}")
        _enabled_channels_cache.clear()

    async def update_channel_defaults(
        self,
        channel_id: str,
        *,
        default_cooldown: int | None = None,
    ) -> Channel | None:
        """Update a channel's default cooldown setting."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE channels SET
                    default_cooldown = COALESCE($2, default_cooldown),
                    updated_at = NOW()
                WHERE channel_id = $1
                RETURNING channel_id, channel_name, enabled,
                          default_cooldown,
                          created_at, updated_at
                """,
                channel_id,
                default_cooldown,
            )
            if not row:
                return None
            result = Channel(**dict(row))
            _channel_cache.invalidate(f"channel:{channel_id}")
            _enabled_channels_cache.clear()
            return result

    # ==================== Discord User Operations ====================

    @cached(
        cache=_discord_user_cache,
        key_func=lambda self, user_id: f"discord_user:{user_id}",
    )
    async def get_discord_user(self, user_id: str) -> DiscordUser | None:
        """Get cached Discord user info."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, username, display_name, avatar, created_at, updated_at "
                "FROM discord_users WHERE user_id = $1",
                user_id,
            )
            if not row:
                return None
            return DiscordUser(**dict(row))

    async def upsert_discord_user(
        self,
        user_id: str,
        username: str,
        display_name: str | None = None,
        avatar: str | None = None,
    ) -> None:
        """Insert or update Discord user info."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO discord_users (user_id, username, display_name, avatar)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET
                    username     = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    avatar       = EXCLUDED.avatar,
                    updated_at   = NOW()
                """,
                user_id,
                username,
                display_name,
                avatar,
            )
        _discord_user_cache.invalidate(f"discord_user:{user_id}")
