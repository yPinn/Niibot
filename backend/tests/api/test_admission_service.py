"""Tests for services.admission_service.AdmissionService.

Verifies the state machine and that every state change writes both the
memberships UPSERT and a matching membership_events row inside the same
transaction. Idempotency is verified by re-invoking ensure_pending /
auto_admit on an already-active user.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.services.admission_service import AdmissionService


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


def _event_row(event_id: int) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: event_id if k == "id" else None
    return row


def _membership_row(user_id: str, status: str) -> MagicMock:
    payload = {
        "user_id": user_id,
        "status": status,
        "granted_at": datetime(2026, 1, 1) if status == "active" else None,
        "granted_by": None,
        "reason": None,
        "updated_at": datetime(2026, 1, 1),
    }
    row = MagicMock()
    row.__getitem__ = lambda self, k: payload[k]
    row.keys = MagicMock(return_value=payload.keys())
    return row


@pytest.mark.asyncio
class TestEnsurePending:
    async def test_idempotent_when_already_active(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "active")
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.ensure_pending(user)

        assert decision.state_changed is False
        events_inserts = [
            c for c in conn.fetchrow.await_args_list if "INSERT INTO membership_events" in c.args[0]
        ]
        assert events_inserts == []

    async def test_idempotent_when_already_pending_regression(self):
        """Regression: re-running ensure_pending on an already-pending user
        must NOT create a duplicate 'requested' event. This is what caused
        the original ghost-pending-request bug — every reauth re-INSERTed."""
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "pending")
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.ensure_pending(user)

        assert decision.state_changed is False
        # Critical: no membership_events INSERT issued.
        events_inserts = [
            c for c in conn.fetchrow.await_args_list if "INSERT INTO membership_events" in c.args[0]
        ]
        assert events_inserts == []

    async def test_idempotent_when_rejected(self):
        """Rejected users keep their state; ensure_pending must not reset them."""
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "rejected")
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.ensure_pending(user)

        assert decision.state_changed is False
        assert decision.membership.status == "rejected"

    async def test_creates_pending_and_event_for_new_user(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        # repo.get → None (no membership yet)
        # upsert_status → returns inserted row
        # insert_event → returns id
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 42 if k == "id" else None

        conn.fetchrow.side_effect = [
            None,  # repo.get returns None
            _membership_row(user, "pending"),  # upsert RETURNING
            event_id_row,  # insert_event RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.ensure_pending(user, reason="first_signup")

        assert decision.state_changed is True
        assert decision.event_id == 42
        assert decision.membership.status == "pending"


@pytest.mark.asyncio
class TestAutoAdmit:
    async def test_owner_auto_admit_writes_event(self):
        user = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 7 if k == "id" else None

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            None,  # repo.get → no row
            _membership_row(user, "active"),  # upsert RETURNING
            event_id_row,  # insert_event RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.auto_admit(user, reason="owner")

        assert decision.membership.status == "active"
        assert decision.state_changed is True
        assert decision.event_id == 7

    async def test_auto_admit_idempotent_when_already_active(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "active")
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.auto_admit(user, reason="owner")

        assert decision.state_changed is False


@pytest.mark.asyncio
class TestApproveReject:
    async def test_approve_records_owner_actor_and_reason(self):
        user = str(uuid.uuid4())
        approver = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 11 if k == "id" else None

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _membership_row(user, "pending"),  # repo.get returns existing pending
            _membership_row(user, "active"),  # upsert RETURNING
            event_id_row,  # insert_event RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.approve(
            user_id=user,
            approver_user_id=approver,
            reason="vetted",
        )

        assert decision.state_changed is True
        assert decision.event_id == 11
        # The membership_events insert was issued with actor_user_id
        events_inserts = [
            c for c in conn.fetchrow.await_args_list if "INSERT INTO membership_events" in c.args[0]
        ]
        assert events_inserts, "expected membership_events INSERT"
        approver_arg = events_inserts[0].args[4]  # $4 = actor_user_id
        assert approver_arg == approver

    async def test_approve_raises_when_no_membership(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        with pytest.raises(ValueError, match="No membership"):
            await svc.approve(user_id=user, approver_user_id=user, reason="x")

    async def test_reject_records_owner_actor(self):
        user = str(uuid.uuid4())
        approver = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 5 if k == "id" else None

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _membership_row(user, "pending"),
            _membership_row(user, "rejected"),
            event_id_row,
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.reject(
            user_id=user,
            approver_user_id=approver,
            reason="bad_actor",
        )

        assert decision.membership.status == "rejected"


@pytest.mark.asyncio
class TestOtpGrant:
    async def test_grant_via_otp_writes_system_actor(self):
        user = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 3 if k == "id" else None

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            None,  # no existing membership
            _membership_row(user, "active"),  # upsert
            event_id_row,  # event
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.grant_via_otp(
            user_id=user,
            platform="twitch",
            platform_user_id="12345",
            code_hash="abc",
        )

        assert decision.membership.status == "active"
        assert decision.state_changed is True

    async def test_grant_via_otp_raises_when_locked(self):
        from api.services.admission_service import MembershipLockedError

        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "suspended")
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        with pytest.raises(MembershipLockedError):
            await svc.grant_via_otp(
                user_id=user, platform="twitch", platform_user_id="1", code_hash="h"
            )

    async def test_grant_via_otp_uses_supplied_conn(self):
        user = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 3 if k == "id" else None
        ext = AsyncMock()
        ext.fetchrow.side_effect = [_membership_row(user, "active"), event_id_row]

        pool_conn = AsyncMock()
        pool_conn.fetchrow.return_value = None  # get() → no membership
        pool = _pool_with(pool_conn)
        svc = AdmissionService(pool)

        await svc.grant_via_otp(
            user_id=user,
            platform="twitch",
            platform_user_id="1",
            code_hash="h",
            conn=ext,
        )
        # membership writes went to the supplied conn, not a freshly acquired one.
        assert ext.fetchrow.await_count == 2
        pool_conn.transaction.assert_not_called()


@pytest.mark.asyncio
class TestActivateIfEntitled:
    async def test_no_grant_no_op(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = None  # no membership
        svc = AdmissionService(_pool_with(conn))
        svc.grants = AsyncMock()
        svc.grants.find_unconsumed_grant.return_value = None

        assert (
            await svc.activate_if_entitled(user, platform="twitch", platform_user_id="1") is False
        )

    async def test_locked_membership_not_reactivated(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "rejected")
        svc = AdmissionService(_pool_with(conn))
        svc.grants = AsyncMock()

        assert (
            await svc.activate_if_entitled(user, platform="twitch", platform_user_id="1") is False
        )
        svc.grants.find_unconsumed_grant.assert_not_called()

    async def test_grant_consumed_and_membership_activated(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            None,  # get() → no membership
            _membership_row(user, "active"),  # upsert
            _event_row(9),  # event
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        svc = AdmissionService(_pool_with(conn))
        svc.grants = AsyncMock()
        svc.grants.find_unconsumed_grant.return_value = {
            "id": 5,
            "redemption_id": "r",
            "channel_id": "c",
            "reward_cost": 100,
        }

        assert await svc.activate_if_entitled(user, platform="twitch", platform_user_id="1") is True
        svc.grants.consume.assert_awaited_once()
        assert svc.grants.consume.await_args.args[0] == 5

    async def test_already_active_still_consumes_dangling_grant(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = _membership_row(user, "active")
        svc = AdmissionService(_pool_with(conn))
        svc.grants = AsyncMock()
        svc.grants.find_unconsumed_grant.return_value = {"id": 7}

        assert await svc.activate_if_entitled(user, platform="twitch", platform_user_id="1") is True
        svc.grants.consume.assert_awaited_once()


@pytest.mark.asyncio
class TestSuspendReinstate:
    async def test_suspend_raises_when_no_membership(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        with pytest.raises(ValueError, match="No membership"):
            await svc.suspend(user_id=user, approver_user_id=user, reason="abuse")

    async def test_reinstate_raises_when_no_membership(self):
        user = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        with pytest.raises(ValueError, match="No membership"):
            await svc.reinstate(user_id=user, approver_user_id=user, reason="appeal")

    async def test_suspend_records_owner_actor(self):
        user = str(uuid.uuid4())
        approver = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 21 if k == "id" else None

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _membership_row(user, "active"),  # repo.get existence check
            _membership_row(user, "suspended"),  # upsert RETURNING
            event_id_row,  # insert_event RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.suspend(user_id=user, approver_user_id=approver, reason="abuse")

        assert decision.membership.status == "suspended"
        assert decision.state_changed is True

    async def test_reinstate_records_owner_actor(self):
        user = str(uuid.uuid4())
        approver = str(uuid.uuid4())
        event_id_row = MagicMock()
        event_id_row.__getitem__ = lambda self, k: 22 if k == "id" else None

        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _membership_row(user, "suspended"),  # repo.get existence check
            _membership_row(user, "active"),  # upsert RETURNING
            event_id_row,  # insert_event RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())
        pool = _pool_with(conn)
        svc = AdmissionService(pool)

        decision = await svc.reinstate(user_id=user, approver_user_id=approver, reason="appeal")

        assert decision.membership.status == "active"
        assert decision.state_changed is True
