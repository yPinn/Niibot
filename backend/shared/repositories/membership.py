"""Repository for memberships + membership_events.

memberships holds the current admission state per user. membership_events is
the append-only audit log; the DB enforces immutability via a trigger so any
attempt to UPDATE/DELETE raises an exception.

This repository is intentionally write-narrow: callers go through
AdmissionService so state changes always carry a matching event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import asyncpg

MembershipStatus = Literal["pending", "active", "suspended", "rejected"]
MembershipEventType = Literal[
    "requested",
    "auto_admitted",
    "approved",
    "rejected",
    "suspended",
    "reinstated",
    "withdrawn",
]
ActorType = Literal["system", "owner", "user"]


@dataclass(frozen=True)
class Membership:
    user_id: str
    status: MembershipStatus
    granted_at: datetime | None
    granted_by: str | None
    reason: str | None
    updated_at: datetime


@dataclass(frozen=True)
class MembershipEvent:
    id: int
    user_id: str
    event_type: MembershipEventType
    actor_type: ActorType
    actor_user_id: str | None
    reason: str | None
    metadata: dict[str, Any]
    occurred_at: datetime


class MembershipRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ---------- memberships ----------

    async def get(self, user_id: str) -> Membership | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id::text AS user_id, status, granted_at,"
                "       granted_by::text AS granted_by, reason, updated_at"
                "  FROM memberships WHERE user_id = $1::uuid",
                user_id,
            )
        return Membership(**dict(row)) if row else None

    async def list_by_status(self, status: MembershipStatus) -> list[Membership]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id::text AS user_id, status, granted_at,"
                "       granted_by::text AS granted_by, reason, updated_at"
                "  FROM memberships WHERE status = $1"
                " ORDER BY updated_at ASC",
                status,
            )
        return [Membership(**dict(r)) for r in rows]

    async def upsert_status(
        self,
        user_id: str,
        status: MembershipStatus,
        *,
        granted_by: str | None = None,
        reason: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Membership:
        """Set or update membership.status. Idempotent re: identical inputs.

        Used by AdmissionService in the same transaction that writes an
        event; passing ``conn`` keeps both writes atomic.
        """
        granted_at_expr = "CASE WHEN $2 = 'active' THEN COALESCE(memberships.granted_at, NOW()) ELSE memberships.granted_at END"
        granted_at_insert = "CASE WHEN $2 = 'active' THEN NOW() ELSE NULL END"
        sql = (
            "INSERT INTO memberships (user_id, status, granted_at, granted_by, reason) "
            f"VALUES ($1::uuid, $2, {granted_at_insert}, $3::uuid, $4) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "  status = EXCLUDED.status,"
            f"  granted_at = {granted_at_expr},"
            "  granted_by = COALESCE(EXCLUDED.granted_by, memberships.granted_by),"
            "  reason     = COALESCE(EXCLUDED.reason,     memberships.reason),"
            "  updated_at = NOW() "
            "RETURNING user_id::text AS user_id, status, granted_at,"
            "          granted_by::text AS granted_by, reason, updated_at"
        )
        args = (user_id, status, granted_by, reason)
        if conn is not None:
            row = await conn.fetchrow(sql, *args)
        else:
            async with self.pool.acquire() as own:
                row = await own.fetchrow(sql, *args)
        return Membership(**dict(row))

    # ---------- events ----------

    async def insert_event(
        self,
        user_id: str,
        event_type: MembershipEventType,
        actor_type: ActorType,
        *,
        actor_user_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> int:
        """Append an admission event. Returns the new event id."""
        import json

        sql = (
            "INSERT INTO membership_events"
            " (user_id, event_type, actor_type, actor_user_id, reason, metadata)"
            " VALUES ($1::uuid, $2, $3, $4::uuid, $5, $6::jsonb)"
            " RETURNING id"
        )
        args = (
            user_id,
            event_type,
            actor_type,
            actor_user_id,
            reason,
            json.dumps(metadata or {}),
        )
        if conn is not None:
            row = await conn.fetchrow(sql, *args)
        else:
            async with self.pool.acquire() as own:
                row = await own.fetchrow(sql, *args)
        return int(row["id"])

    async def list_events_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
    ) -> list[MembershipEvent]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, user_id::text AS user_id, event_type, actor_type,"
                "       actor_user_id::text AS actor_user_id, reason, metadata,"
                "       occurred_at"
                "  FROM membership_events"
                " WHERE user_id = $1::uuid"
                " ORDER BY occurred_at DESC, id DESC"
                " LIMIT $2",
                user_id,
                limit,
            )
        return [MembershipEvent(**dict(r)) for r in rows]

    async def latest_event_type(
        self,
        user_id: str,
    ) -> MembershipEventType | None:
        """Return the most recent event_type for a user, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT event_type FROM membership_events"
                " WHERE user_id = $1::uuid"
                " ORDER BY occurred_at DESC, id DESC LIMIT 1",
                user_id,
            )
        return row["event_type"] if row else None
