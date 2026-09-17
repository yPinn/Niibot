"""TenantService — channel (tenant) lifecycle + access enforcement.

A "tenant" in Niibot is one Twitch broadcaster's workspace, modelled by a
``channels`` row. Each tenant has exactly one owner User and may have
manager/viewer collaborators in ``channel_members``.

This service is the single source of truth for:
  * "who owns / can manage channel X" — used by require_tenant_access
  * "list every channel I have any role in" — used by dashboard
  * "create the tenant when a broadcaster first activates" — wired from
    the OAuth callback so each owner -> channel binding is set up exactly
    once and recorded in channel_members.

Tenant suspension (channels.suspended_at) is exposed but currently has no
UI surface — it's reserved for operator-initiated take-downs that should
not require touching the owner's membership.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import asyncpg

from shared.errors import AccessDeniedError, AppError, NotFoundError
from shared.repositories.channel_member import (
    ChannelMember,
    ChannelMemberRepository,
    role_satisfies,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

TenantRole = Literal["owner", "manager", "viewer"]


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant access for the current request."""

    channel_id: str
    user_id: str
    role: TenantRole
    #: Login, bound into the log context so API log lines identify the tenant
    #: by name instead of only a numeric id. Optional (not None-free) so the
    #: contextvar is simply skipped when a caller builds a context without it.
    channel_name: str | None = None


@dataclass(frozen=True)
class TenantSummary:
    """Safe workspace metadata returned by the tenant picker API."""

    channel_id: str
    channel_name: str
    display_name: str | None
    enabled: bool
    role: TenantRole


class TenantNotFoundError(NotFoundError):
    """Raised when channel_id does not exist."""

    code = "TENANT.NOT_FOUND"
    user_message = "找不到這個頻道"


class TenantSuspendedError(AppError):
    """Raised when a tenant has been operator-suspended."""

    code = "TENANT.SUSPENDED"
    http_status = 403
    user_message = "這個頻道已被停用"
    log_level = logging.WARNING


class TenantAccessDeniedError(AccessDeniedError):
    """Raised when a user does not have the required role on a channel."""

    code = "TENANT.ACCESS_DENIED"
    user_message = "你不是這個頻道的成員"


class TenantAccountLockedError(AccessDeniedError):
    """The identity is globally suspended/rejected despite a tenant grant."""

    code = "TENANT.ACCOUNT_LOCKED"
    user_message = "你的帳號目前無法使用協作功能"


class TenantService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.members = ChannelMemberRepository(pool)

    # ------------------------------------------------------------------
    # Tenant lifecycle
    # ------------------------------------------------------------------

    async def ensure_tenant_for_owner(
        self,
        *,
        channel_id: str,
        owner_user_id: str,
        channel_name: str,
        display_name: str | None = None,
    ) -> None:
        """Idempotently set up the (channel, owner) pair after a successful login.

        Creates the channels row if missing, sets owner_user_id if NULL,
        and seeds channel_members with role='owner'.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO channels
                        (channel_id, channel_name, display_name, owner_user_id, enabled)
                    VALUES ($1, $2, $3, $4::uuid, TRUE)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name  = EXCLUDED.channel_name,
                        display_name  = COALESCE(EXCLUDED.display_name, channels.display_name),
                        owner_user_id = COALESCE(channels.owner_user_id, EXCLUDED.owner_user_id),
                        updated_at    = NOW()
                    """,
                    channel_id,
                    channel_name,
                    display_name,
                    owner_user_id,
                )
                await self.members.upsert(
                    channel_id=channel_id,
                    user_id=owner_user_id,
                    role="owner",
                    granted_by=owner_user_id,
                    conn=conn,
                )

    async def suspend_tenant(self, channel_id: str, reason: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE channels SET suspended_at = NOW(), suspended_reason = $2"
                " WHERE channel_id = $1",
                channel_id,
                reason,
            )

    async def unsuspend_tenant(self, channel_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE channels SET suspended_at = NULL, suspended_reason = NULL"
                " WHERE channel_id = $1",
                channel_id,
            )

    # ------------------------------------------------------------------
    # Access checks
    # ------------------------------------------------------------------

    async def assert_access(
        self,
        *,
        channel_id: str,
        user_id: str,
        required_role: TenantRole = "manager",
    ) -> TenantContext:
        """Verify caller is a tenant member with at least required_role.

        Raises TenantNotFoundError / TenantSuspendedError / TenantAccessDeniedError.
        On success returns a TenantContext describing the resolved role.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.channel_id,
                       c.channel_name,
                       c.suspended_at,
                       cm.role,
                       caller_membership.status AS caller_membership_status,
                       owner_membership.status AS owner_membership_status
                  FROM channels c
                  LEFT JOIN channel_members cm
                    ON cm.channel_id = c.channel_id
                   AND cm.user_id = $2::uuid
                  LEFT JOIN memberships caller_membership
                    ON caller_membership.user_id = $2::uuid
                  LEFT JOIN memberships owner_membership
                    ON owner_membership.user_id = c.owner_user_id
                 WHERE c.channel_id = $1
                """,
                channel_id,
                user_id,
            )
        # Deliberately return the same 404 for a missing tenant and a caller
        # who is not a member, preventing channel-id enumeration.
        if row is None or row["role"] is None:
            raise TenantNotFoundError(context={"channel_id": channel_id})
        if row["caller_membership_status"] in {"suspended", "rejected"}:
            raise TenantAccountLockedError(context={"user_id": user_id})
        if row["suspended_at"] is not None:
            raise TenantSuspendedError(context={"channel_id": channel_id})
        if row["owner_membership_status"] != "active":
            raise TenantSuspendedError(context={"channel_id": channel_id})

        role = str(row["role"])
        if not role_satisfies(role, required_role):
            raise TenantAccessDeniedError(context={"channel_id": channel_id, "user_id": user_id})
        return TenantContext(
            channel_id=channel_id,
            user_id=user_id,
            role=role,  # type: ignore[arg-type]
            channel_name=row["channel_name"],
        )

    async def list_user_tenants(self, user_id: str) -> list[ChannelMember]:
        """Every channel the user has any role in (dashboard tenant picker)."""
        return await self.members.list_for_user(user_id)

    async def list_accessible_tenants(self, user_id: str) -> list[TenantSummary]:
        """Return non-suspended workspaces whose owner remains admitted."""
        async with self.pool.acquire() as conn:
            caller_status = await conn.fetchval(
                "SELECT status FROM memberships WHERE user_id = $1::uuid",
                user_id,
            )
            if caller_status in {"suspended", "rejected"}:
                raise TenantAccountLockedError(context={"user_id": user_id})

            rows = await conn.fetch(
                """
                SELECT c.channel_id,
                       c.channel_name,
                       c.display_name,
                       c.enabled,
                       cm.role
                  FROM channel_members cm
                  JOIN channels c
                    ON c.channel_id = cm.channel_id
                  JOIN memberships owner_membership
                    ON owner_membership.user_id = c.owner_user_id
                 WHERE cm.user_id = $1::uuid
                   AND c.suspended_at IS NULL
                   AND owner_membership.status = 'active'
                 ORDER BY CASE cm.role WHEN 'owner' THEN 0 ELSE 1 END,
                          cm.granted_at ASC,
                          c.channel_id ASC
                """,
                user_id,
            )
        return [TenantSummary(**dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Postgres RLS binding (Phase 3)
    # ------------------------------------------------------------------

    async def bind_session(
        self,
        conn: asyncpg.Connection,
        channel_id: str,
    ) -> None:
        """Set the per-session GUC consulted by RLS policies.

        Must be called within the same transaction as subsequent queries
        that should be RLS-scoped. Safe to call even when RLS is disabled
        (Postgres just stores the value).
        """
        await conn.execute(
            "SELECT set_config('app.current_channel_id', $1, true)",
            channel_id,
        )
