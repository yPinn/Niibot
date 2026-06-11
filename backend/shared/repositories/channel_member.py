"""Repository for channel_members — per-tenant RBAC.

Each row says "this User has this role inside this Channel". The 'owner' role
is enforced as one-per-channel by a partial UNIQUE index on the table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import asyncpg

ChannelRole = Literal["owner", "manager", "viewer"]

# Role hierarchy: a role satisfies its own check + every weaker check.
_ROLE_RANK: dict[str, int] = {"owner": 3, "manager": 2, "viewer": 1}


def role_satisfies(actual: str, required: str) -> bool:
    """Return True if `actual` role is at least as strong as `required`."""
    return _ROLE_RANK.get(actual, 0) >= _ROLE_RANK.get(required, 0)


@dataclass(frozen=True)
class ChannelMember:
    channel_id: str
    user_id: str
    role: ChannelRole
    granted_at: datetime
    granted_by: str | None


class ChannelMemberRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get(self, channel_id: str, user_id: str) -> ChannelMember | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT channel_id, user_id::text AS user_id, role,"
                "       granted_at, granted_by::text AS granted_by"
                "  FROM channel_members"
                " WHERE channel_id = $1 AND user_id = $2::uuid",
                channel_id,
                user_id,
            )
        return ChannelMember(**dict(row)) if row else None

    async def list_for_user(self, user_id: str) -> list[ChannelMember]:
        """All channels a user has any role in."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT channel_id, user_id::text AS user_id, role,"
                "       granted_at, granted_by::text AS granted_by"
                "  FROM channel_members"
                " WHERE user_id = $1::uuid"
                " ORDER BY granted_at ASC",
                user_id,
            )
        return [ChannelMember(**dict(r)) for r in rows]

    async def list_for_channel(self, channel_id: str) -> list[ChannelMember]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT channel_id, user_id::text AS user_id, role,"
                "       granted_at, granted_by::text AS granted_by"
                "  FROM channel_members"
                " WHERE channel_id = $1"
                " ORDER BY granted_at ASC",
                channel_id,
            )
        return [ChannelMember(**dict(r)) for r in rows]

    async def upsert(
        self,
        channel_id: str,
        user_id: str,
        role: ChannelRole,
        *,
        granted_by: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> ChannelMember:
        sql = (
            "INSERT INTO channel_members (channel_id, user_id, role, granted_by)"
            " VALUES ($1, $2::uuid, $3, $4::uuid)"
            " ON CONFLICT (channel_id, user_id) DO UPDATE SET"
            "   role = EXCLUDED.role,"
            "   granted_by = COALESCE(EXCLUDED.granted_by, channel_members.granted_by)"
            " RETURNING channel_id, user_id::text AS user_id, role,"
            "          granted_at, granted_by::text AS granted_by"
        )
        args = (channel_id, user_id, role, granted_by)
        if conn is not None:
            row = await conn.fetchrow(sql, *args)
        else:
            async with self.pool.acquire() as own:
                row = await own.fetchrow(sql, *args)
        return ChannelMember(**dict(row))

    async def remove(self, channel_id: str, user_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM channel_members WHERE channel_id = $1 AND user_id = $2::uuid",
                channel_id,
                user_id,
            )
        return result != "DELETE 0"
