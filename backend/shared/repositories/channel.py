"""Repository for tokens, channels, and discord_users tables."""

from __future__ import annotations

import logging
import os

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.channel import Channel, DiscordUser, Token
from shared.twitch_token_crypto import decrypt_twitch_token, encrypt_twitch_token

LOGGER: logging.Logger = logging.getLogger(__name__)

# --- In-process caches ---
# Long TTL for memory-first reads. Freshness: `_channel_cache` /
# `_enabled_channels_cache` are invalidated on `channel_toggle`/`config_change`
# pg_notify (both twitch and api processes listen — see core/_notify_mixin.py
# and api/app.py) plus a periodic full-clear safety net. `_token_cache` has its
# own `new_token`/`token_reauth` notify flow and is NOT part of that safety net.
_token_cache = AsyncTTLCache(maxsize=64, ttl=3600, name="channel.token")
_channel_cache = AsyncTTLCache(maxsize=64, ttl=3600, name="channel.channel")
_enabled_channels_cache = AsyncTTLCache(maxsize=1, ttl=3600, name="channel.enabled_channels")
_discord_user_cache = AsyncTTLCache(maxsize=64, ttl=300, name="channel.discord_user")
# Short TTL: only feeds the log viewer's id -> login resolution, where a few
# minutes of staleness costs nothing but a rename showing late.
_channel_name_cache = AsyncTTLCache(maxsize=1, ttl=300, name="channel.name_map")


class ChannelRepository:
    """Pure SQL operations for tokens / channels / discord_users."""

    def __init__(self, pool: asyncpg.Pool, *, token_encryption_key: str | None = None) -> None:
        self.pool = pool
        self._token_encryption_key = token_encryption_key or os.getenv(
            "TWITCH_TOKEN_ENCRYPTION_KEY"
        )

    def _encode_token_pair(self, token: str, refresh: str) -> tuple[str, str, int]:
        if not self._token_encryption_key:
            return token, refresh, 0
        encrypted_token, version = encrypt_twitch_token(token, self._token_encryption_key)
        encrypted_refresh, refresh_version = encrypt_twitch_token(
            refresh, self._token_encryption_key
        )
        if refresh_version != version:  # pragma: no cover - defensive future-version guard
            raise RuntimeError("Twitch token and refresh encryption versions diverged")
        return encrypted_token, encrypted_refresh, version

    def _decode_token_row(self, row: asyncpg.Record | dict) -> Token:
        data = dict(row)
        version = int(data.pop("encryption_version", 0))
        data["token"] = decrypt_twitch_token(
            data["token"], version=version, key=self._token_encryption_key
        )
        data["refresh"] = decrypt_twitch_token(
            data["refresh"], version=version, key=self._token_encryption_key
        )
        return Token(**data)

    # ==================== Token Operations ====================

    @property
    def token_encryption_key(self) -> str:
        """Configured key for services that share this repository boundary."""
        return self._token_encryption_key or ""

    @staticmethod
    def invalidate_token(user_id: str, token_type: str = "broadcaster") -> None:
        _token_cache.invalidate(f"token:{user_id}:{token_type}")

    @cached(
        cache=_token_cache,
        key_func=lambda self, user_id, token_type="broadcaster": f"token:{user_id}:{token_type}",
    )
    async def get_token(self, user_id: str, token_type: str = "broadcaster") -> Token | None:
        """Get a user's OAuth token by type ('broadcaster' or 'bot')."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, token, refresh, token_type, scopes, credential_revision, "
                "encryption_version, "
                "created_at, updated_at "
                "FROM tokens WHERE user_id = $1 AND token_type = $2",
                user_id,
                token_type,
            )
            if not row:
                return None
            return self._decode_token_row(row)

    async def upsert_token_only(
        self,
        user_id: str,
        token: str,
        refresh: str,
        scopes: str | None = None,
        token_type: str = "broadcaster",
    ) -> None:
        """Insert or update an OAuth token (without touching the channels table)."""
        encrypted_token, encrypted_refresh, encryption_version = self._encode_token_pair(
            token, refresh
        )
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tokens (
                    user_id, token, refresh, scopes, token_type, encryption_version,
                    last_checked_at, last_validated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                ON CONFLICT (user_id, token_type) DO UPDATE SET
                    token              = EXCLUDED.token,
                    refresh            = EXCLUDED.refresh,
                    scopes             = COALESCE(EXCLUDED.scopes, tokens.scopes),
                    encryption_version = EXCLUDED.encryption_version,
                    requires_reauth    = FALSE,
                    reauth_notified_at = NULL,
                    last_checked_at    = NOW(),
                    last_validated_at  = NOW(),
                    invalidated_at     = NULL,
                    validation_error_code = NULL,
                    credential_revision = tokens.credential_revision + 1,
                    updated_at         = NOW()
                """,
                user_id,
                encrypted_token,
                encrypted_refresh,
                scopes,
                token_type,
                encryption_version,
            )
        _token_cache.invalidate(f"token:{user_id}:{token_type}")

    async def mark_requires_reauth(
        self,
        user_id: str,
        token_type: str = "broadcaster",
        *,
        expected_revision: int | None = None,
    ) -> bool:
        """Flag a token for re-auth; /auth/user checks this to force re-login, cleared by upsert_token."""
        async with self.pool.acquire() as conn:
            if expected_revision is None:
                result = await conn.execute(
                    "UPDATE tokens SET requires_reauth = TRUE, reauth_notified_at = NOW() "
                    "WHERE user_id = $1 AND token_type = $2",
                    user_id,
                    token_type,
                )
            else:
                result = await conn.execute(
                    "UPDATE tokens SET requires_reauth = TRUE, reauth_notified_at = NOW() "
                    "WHERE user_id = $1 AND token_type = $2 AND credential_revision = $3",
                    user_id,
                    token_type,
                    expected_revision,
                )
        _token_cache.invalidate(f"token:{user_id}:{token_type}")
        return str(result).endswith(" 1")

    async def list_tokens(self) -> list[Token]:
        """Return all tokens (both types)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, token, refresh, token_type, scopes, credential_revision, "
                "encryption_version, "
                "requires_reauth, reauth_notified_at, created_at, updated_at "
                "FROM tokens"
            )
            return [self._decode_token_row(r) for r in rows]

    async def upsert_token(
        self,
        user_id: str,
        token: str,
        refresh: str,
        channel_name: str = "",
        scopes: str | None = None,
        display_name: str | None = None,
        token_type: str = "broadcaster",
    ) -> None:
        """Insert or update an OAuth token and ensure a channels row exists.

        This is a single transaction: tokens upsert + channels upsert.
        """
        encrypted_token, encrypted_refresh, encryption_version = self._encode_token_pair(
            token, refresh
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO tokens (
                        user_id, token, refresh, scopes, token_type, encryption_version,
                        last_checked_at, last_validated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                    ON CONFLICT (user_id, token_type) DO UPDATE SET
                        token           = EXCLUDED.token,
                        refresh         = EXCLUDED.refresh,
                        scopes          = COALESCE(EXCLUDED.scopes, tokens.scopes),
                        encryption_version = EXCLUDED.encryption_version,
                        requires_reauth = FALSE,
                        reauth_notified_at = NULL,
                        last_checked_at = NOW(),
                        last_validated_at = NOW(),
                        invalidated_at = NULL,
                        validation_error_code = NULL,
                        credential_revision = tokens.credential_revision + 1,
                        updated_at      = NOW()
                    """,
                    user_id,
                    encrypted_token,
                    encrypted_refresh,
                    scopes,
                    token_type,
                    encryption_version,
                )
                # enabled is intentionally omitted so the row uses the column
                # default (FALSE). Admission — not signup — turns a channel on
                # (see migration 084). ON CONFLICT must NOT touch enabled either,
                # so a re-auth never re-enables a suspended/pending channel.
                await conn.execute(
                    """
                    INSERT INTO channels (channel_id, channel_name, display_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        display_name = COALESCE(EXCLUDED.display_name, channels.display_name),
                        updated_at   = NOW()
                    """,
                    user_id,
                    channel_name,
                    display_name,
                )

        _token_cache.invalidate(f"token:{user_id}:{token_type}")
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

    @cached(cache=_channel_name_cache, key_func=lambda self: "channel_names")
    async def get_channel_name_map(self) -> dict[str, str]:
        """``channel_id -> channel_name`` for every channel, disabled included —
        a suspended channel is exactly when you need to know whose it is.

        Resolves the numeric channel ids that appear in log lines back to
        logins (see ``api/routers/admin/logs.py``). Deliberately its own
        narrow query rather than reusing ``list_all_channels()`` so the log
        viewer never pulls whole Channel rows it has no use for.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT channel_id, channel_name FROM channels")
            return {r["channel_id"]: r["channel_name"] for r in rows if r["channel_name"]}

    async def list_all_channels(self) -> list[Channel]:
        """Return all channels (including disabled)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT channel_id, channel_name, enabled, default_cooldown,created_at, updated_at FROM channels"
            )
            return [Channel(**dict(r)) for r in rows]

    async def list_active_owner_channel_ids(self) -> set[str]:
        """Channel IDs whose owner has an 'active' membership (admission gate).

        Used by the admin monitored-channels view to exclude tenants that are
        still pending / suspended / rejected. A channel can be in this set while
        disabled (an active owner who manually paused the bot), so callers must
        not conflate it with ``enabled``.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.channel_id
                  FROM channels c
                  JOIN memberships m ON m.user_id = c.owner_user_id
                 WHERE m.status = 'active'
                """
            )
            return {r["channel_id"] for r in rows}

    async def list_monitored_owner_channel_status(
        self,
    ) -> dict[str, tuple[str, str, str | None]]:
        """channel_id -> (membership status, owner_user_id, reason) for the admin grid.

        Includes active / pending / suspended owners (excludes rejected, which
        has no monitoring value) so the admin UI can surface channels awaiting
        review or that were suspended, not just active tenants. Pending and
        suspended owners already have a channels row by this point — the OAuth
        callback links owner_user_id before/alongside the membership row, see
        docs/architecture/admission-and-tenancy.md.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.channel_id,
                       m.status,
                       c.owner_user_id::text AS owner_user_id,
                       m.reason
                  FROM channels c
                  JOIN memberships m ON m.user_id = c.owner_user_id
                 WHERE m.status IN ('active', 'pending', 'suspended')
                """
            )
            return {r["channel_id"]: (r["status"], r["owner_user_id"], r["reason"]) for r in rows}

    async def upsert_channel(
        self, channel_id: str, channel_name: str, enabled: bool = True
    ) -> None:
        """Insert or update a channel row.

        ON CONFLICT deliberately does NOT touch ``enabled``: a channel's monitored
        state is owned by admission (migration 084), so re-asserting a channel
        row (e.g. the bot processing a new_token) must never re-enable a
        suspended/pending channel. The ``enabled`` argument only applies when a
        brand-new row is inserted.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channels (channel_id, channel_name, enabled)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
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

    async def get_broadcaster_display_name(self, channel_id: str) -> str | None:
        """Return display_name (or username) for the linked Twitch account."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT u.display_name, la.username "
                "FROM user_linked_accounts la "
                "JOIN users u ON u.id = la.user_id "
                "WHERE la.platform = 'twitch' AND la.platform_user_id = $1",
                channel_id,
            )
            if not row:
                return None
            return row["display_name"] or row["username"]

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
