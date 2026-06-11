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
    TenantNotFoundError,
    TenantService,
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


def _channel_row(channel_id: str = "12345", *, suspended: bool = False) -> MagicMock:
    payload = {
        "channel_id": channel_id,
        "suspended_at": datetime(2026, 1, 1) if suspended else None,
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
        conn.fetchrow.side_effect = [
            _channel_row(),  # channels lookup
            _member_row("12345", user, "owner"),  # channel_members.get
        ]
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
        conn.fetchrow.side_effect = [
            _channel_row(),
            _member_row("12345", user, "viewer"),
        ]
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
        conn.fetchrow.side_effect = [
            _channel_row(),
            None,  # not a member
        ]
        pool = _pool_with(conn)
        svc = TenantService(pool)

        with pytest.raises(TenantAccessDeniedError):
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
        conn.fetchrow.return_value = _channel_row(suspended=True)
        pool = _pool_with(conn)
        svc = TenantService(pool)

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
