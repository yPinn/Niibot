"""Repository for identities table — stable platform identity layer.

Replaces direct access to `user_linked_accounts` (now aliased as a view).
Every identity row pairs a (platform, platform_user_id) with a User UUID
and carries a stable `id` of its own so credentials and audit events can
FK to it without coupling to platform IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Identity:
    id: str
    user_id: str
    platform: str
    platform_user_id: str
    username: str | None
    linked_at: datetime
    last_seen_at: datetime


class IdentityRepository:
    """Pure SQL operations for the identities table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def find_by_platform_id(
        self,
        platform: str,
        platform_user_id: str,
    ) -> Identity | None:
        """Return the identity for a given platform pair, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id::text AS id, user_id::text AS user_id, platform,"
                "       platform_user_id, username, linked_at, last_seen_at"
                "  FROM identities"
                " WHERE platform = $1 AND platform_user_id = $2",
                platform,
                platform_user_id,
            )
        return Identity(**dict(row)) if row else None

    async def list_for_user(self, user_id: str) -> list[Identity]:
        """All identities linked to a user (multi-platform aware)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id::text AS id, user_id::text AS user_id, platform,"
                "       platform_user_id, username, linked_at, last_seen_at"
                "  FROM identities"
                " WHERE user_id = $1::uuid"
                " ORDER BY linked_at ASC",
                user_id,
            )
        return [Identity(**dict(r)) for r in rows]

    async def insert_for_user(
        self,
        user_id: str,
        platform: str,
        platform_user_id: str,
        username: str,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> Identity:
        """Insert a new identity row for an existing user.

        Accepts an optional ``conn`` so callers in a transaction can share it
        (used by IdentityService when linking inside find_or_link).
        Raises asyncpg.UniqueViolationError on (platform, platform_user_id)
        collision — callers should fall back to find_by_platform_id then.
        """
        sql = (
            "INSERT INTO identities"
            " (user_id, platform, platform_user_id, username)"
            " VALUES ($1::uuid, $2, $3, $4)"
            " RETURNING id::text AS id, user_id::text AS user_id, platform,"
            "          platform_user_id, username, linked_at, last_seen_at"
        )
        args = (user_id, platform, platform_user_id, username)
        if conn is not None:
            row = await conn.fetchrow(sql, *args)
        else:
            async with self.pool.acquire() as own:
                row = await own.fetchrow(sql, *args)
        return Identity(**dict(row))

    async def touch_last_seen(self, identity_id: str) -> None:
        """Bump last_seen_at for an identity. Called on every successful login."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE identities SET last_seen_at = NOW() WHERE id = $1::uuid",
                identity_id,
            )

    async def update_username(self, identity_id: str, username: str) -> None:
        """Sync platform username (Twitch login can change over time)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE identities SET username = $1 WHERE id = $2::uuid",
                username,
                identity_id,
            )
