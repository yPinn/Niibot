"""Tests for services.tenant_service.TenantService.

Covers ensure_tenant_for_owner idempotency and assert_access in all three
failure modes (not found / suspended / access denied) plus the success path.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.services.tenant_service import (
    TenantAccessDeniedError,
    TenantAccountLockedError,
    TenantNotFoundError,
    TenantService,
    TenantSummary,
    TenantSuspendedError,
)


def _pool_with(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _tx_cm() -> MagicMock:
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    return tx


def _access_row(
    channel_id: str = "12345",
    *,
    role: str | None = "owner",
    suspended: bool = False,
    caller_status: str | None = "active",
    owner_status: str | None = "active",
) -> MagicMock:
    payload = {
        "channel_id": channel_id,
        "suspended_at": datetime(2026, 1, 1) if suspended else None,
        "role": role,
        "caller_membership_status": caller_status,
        "owner_membership_status": owner_status,
    }
    row = MagicMock()
    row.__getitem__ = lambda self, k: payload[k]
    return row


def _member_row(channel_id: str, user_id: str, role: str) -> MagicMock:
    payload = {
        "channel_id": channel_id,
        "user_id": user_id,
        "role": role,
        "granted_at": datetime(2026, 1, 1),
        "granted_by": None,
    }
    row = MagicMock()
    row.__getitem__ = lambda self, k: payload[k]
    row.keys = MagicMock(return_value=payload.keys())
    return row


@pytest.mark.asyncio
class TestAssertAccess:
    async def test_owner_role_satisfies_manager_requirement(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(role="owner")
        pool = _pool_with(conn)
        svc = TenantService(pool)

        ctx = await svc.assert_access(
            channel_id="12345",
            user_id=user,
            required_role="manager",
        )
        assert ctx.role == "owner"

    async def test_viewer_role_insufficient_for_manager(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(role="viewer")
        pool = _pool_with(conn)
        svc = TenantService(pool)

        with pytest.raises(TenantAccessDeniedError):
            await svc.assert_access(
                channel_id="12345",
                user_id=user,
                required_role="manager",
            )

    async def test_non_member_denied(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(role=None)
        pool = _pool_with(conn)
        svc = TenantService(pool)

        with pytest.raises(TenantNotFoundError):
            await svc.assert_access(
                channel_id="12345",
                user_id=str(uuid.uuid4()),
                required_role="viewer",
            )

    async def test_missing_channel_raises_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None  # channels lookup empty
        pool = _pool_with(conn)
        svc = TenantService(pool)

        with pytest.raises(TenantNotFoundError):
            await svc.assert_access(
                channel_id="ghost",
                user_id=str(uuid.uuid4()),
            )

    async def test_suspended_channel_raises(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(suspended=True)
        pool = _pool_with(conn)
        svc = TenantService(pool)

        with pytest.raises(TenantSuspendedError):
            await svc.assert_access(
                channel_id="12345",
                user_id=str(uuid.uuid4()),
            )

    @pytest.mark.parametrize("status", ["suspended", "rejected"])
    async def test_globally_locked_collaborator_is_denied(self, status: str):
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(role="manager", caller_status=status)
        svc = TenantService(_pool_with(conn))

        with pytest.raises(TenantAccountLockedError):
            await svc.assert_access(
                channel_id="12345",
                user_id=str(uuid.uuid4()),
            )

    async def test_collaborator_without_broadcaster_membership_is_allowed(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(role="manager", caller_status=None)
        svc = TenantService(_pool_with(conn))

        ctx = await svc.assert_access(channel_id="12345", user_id=user)

        assert ctx.role == "manager"

    async def test_inactive_owner_suspends_workspace_for_mods(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _access_row(
            role="manager", caller_status=None, owner_status="suspended"
        )
        svc = TenantService(_pool_with(conn))

        with pytest.raises(TenantSuspendedError):
            await svc.assert_access(
                channel_id="12345",
                user_id=str(uuid.uuid4()),
            )


@pytest.mark.asyncio
class TestEnsureTenantForOwner:
    async def test_inserts_channel_and_owner_membership(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.transaction = MagicMock(return_value=_tx_cm())
        # ChannelMemberRepository.upsert RETURNING
        conn.fetchrow.return_value = _member_row("12345", user, "owner")

        pool = _pool_with(conn)
        svc = TenantService(pool)

        await svc.ensure_tenant_for_owner(
            channel_id="12345",
            owner_user_id=user,
            channel_name="alice",
            display_name="Alice",
        )

        # First execute: channels UPSERT; second: channel_members UPSERT (via fetchrow)
        executed_sqls = " ".join(call.args[0] for call in conn.execute.await_args_list)
        assert "INSERT INTO channels" in executed_sqls
        # channel_members goes through repo.upsert which uses fetchrow with RETURNING
        member_inserts = [
            c for c in conn.fetchrow.await_args_list if "INSERT INTO channel_members" in c.args[0]
        ]
        assert member_inserts, "expected channel_members upsert"


@pytest.mark.asyncio
class TestListAccessibleTenants:
    async def test_returns_channel_metadata_and_role_for_workspace_picker(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetch.return_value = [
            {
                "channel_id": "12345",
                "channel_name": "alice",
                "display_name": "Alice",
                "enabled": True,
                "role": "manager",
            }
        ]
        svc = TenantService(_pool_with(conn))

        tenants = await svc.list_accessible_tenants(user)

        assert tenants == [
            TenantSummary(
                channel_id="12345",
                channel_name="alice",
                display_name="Alice",
                enabled=True,
                role="manager",
            )
        ]
        assert "owner_membership.status = 'active'" in conn.fetch.await_args.args[0]

    @pytest.mark.parametrize("status", ["suspended", "rejected"])
    async def test_locked_account_cannot_list_workspaces(self, status: str):
        conn = AsyncMock()
        conn.fetchval.return_value = status
        svc = TenantService(_pool_with(conn))

        with pytest.raises(TenantAccountLockedError):
            await svc.list_accessible_tenants(str(uuid.uuid4()))

        conn.fetch.assert_not_awaited()
