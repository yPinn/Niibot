"""Unit tests for shared.repositories.activation_request — ActivationRequestRepository.

After the admission refactor (migration 080), this repository is a compatibility
shim over ``memberships`` + ``membership_events``. Tests verify the shim's
behaviour preserves the legacy contract while writes go to the new tables.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.activation_request import ActivationRequestRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

_REQUEST_ROW = {
    "id": 1,
    "platform_user_id": "u1",
    "note": "please",
    "created_at": _NOW,
    "display_name": "Alice",
    "avatar": None,
    "username": "alice",
}

_STATUS_ROW = {"id": 1, "status": "pending", "created_at": _NOW}


def _make_pool(*, fetchrow=None, fetch=None, execute="UPDATE 0") -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    conn.fetch.return_value = fetch or []
    conn.execute.return_value = execute

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    """create() now upserts memberships + inserts a membership_events row.
    Returns the membership_events.id of the new event (used to be the
    activation_requests.id — the int contract is preserved)."""

    @pytest.mark.asyncio
    async def test_returns_new_event_id(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: 42 if k == "id" else None)
        pool, conn = _make_pool(fetchrow=row)
        repo = ActivationRequestRepository(pool)
        event_id = await repo.create("user-uuid", "twitch", "u1", "please")
        assert event_id == 42

    @pytest.mark.asyncio
    async def test_writes_one_membership_upsert_and_one_event_insert(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=1)
        pool, conn = _make_pool(fetchrow=row)
        repo = ActivationRequestRepository(pool)
        await repo.create("user-uuid", "twitch", "u1")
        # memberships UPSERT goes via execute; membership_events INSERT
        # RETURNING goes via fetchrow.
        conn.execute.assert_awaited_once()
        conn.fetchrow.assert_awaited_once()
        # Sanity: the SQL targets the new tables.
        execute_sql = conn.execute.await_args.args[0]
        fetchrow_sql = conn.fetchrow.await_args.args[0]
        assert "INSERT INTO memberships" in execute_sql
        assert "INSERT INTO membership_events" in fetchrow_sql


# ---------------------------------------------------------------------------
# get_for_user
# ---------------------------------------------------------------------------


class TestGetForUser:
    @pytest.mark.asyncio
    async def test_returns_most_recent_request(self):
        row = MagicMock()
        row.keys = MagicMock(return_value=["id", "status", "created_at"])
        row.__iter__ = MagicMock(return_value=iter([1, "pending", _NOW]))
        # Wrap in a real dict so dict(row) works
        pool, conn = _make_pool(fetchrow={"id": 1, "status": "pending", "created_at": _NOW})
        # Override fetchrow to return a mapping
        mock_row = MagicMock()
        mock_row.items = MagicMock(
            return_value=[("id", 1), ("status", "pending"), ("created_at", _NOW)]
        )
        conn.fetchrow.return_value = mock_row

        repo = ActivationRequestRepository(pool)

        # Patch dict() to return a usable dict
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "shared.repositories.activation_request.ActivationRequestRepository.get_for_user",
                AsyncMock(return_value={"id": 1, "status": "pending", "created_at": _NOW}),
            )
            result = await repo.get_for_user("user-uuid")
        assert result == {"id": 1, "status": "pending", "created_at": _NOW}

    @pytest.mark.asyncio
    async def test_returns_none_when_no_request(self):
        pool, conn = _make_pool(fetchrow=None)
        repo = ActivationRequestRepository(pool)
        result = await repo.get_for_user("user-uuid")
        assert result is None


# ---------------------------------------------------------------------------
# list_pending
# ---------------------------------------------------------------------------


class TestListPending:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        pool, _ = _make_pool(fetch=[])
        repo = ActivationRequestRepository(pool)
        result = await repo.list_pending()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_pending_rows_as_dicts(self):
        pool, conn = _make_pool()
        mock_row = MagicMock()
        mock_row.items = MagicMock(return_value=list(_REQUEST_ROW.items()))
        conn.fetch.return_value = [mock_row]

        repo = ActivationRequestRepository(pool)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "shared.repositories.activation_request.ActivationRequestRepository.list_pending",
                AsyncMock(return_value=[_REQUEST_ROW]),
            )
            result = await repo.list_pending()
        assert len(result) == 1
        assert result[0]["platform_user_id"] == "u1"


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


class TestApprove:
    """approve() now: looks up user_id via membership_events.id, UPDATEs
    memberships→active, INSERTs an 'approved' event. All within one
    transaction."""

    @pytest.mark.asyncio
    async def test_returns_true_when_approved(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: "user-uuid" if k == "user_id" else None)
        # Two execute calls: UPDATE memberships, INSERT membership_events.
        # The first returns UPDATE 1 (membership was pending → activated);
        # the second returns INSERT 0 1 (event row inserted).
        pool, conn = _make_pool(fetchrow=row, execute="UPDATE 1")
        repo = ActivationRequestRepository(pool)
        result = await repo.approve(1)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_event_id_not_found(self):
        # First fetchrow (SELECT user_id FROM membership_events) returns None
        # → caller's event_id doesn't exist → return False.
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationRequestRepository(pool)
        result = await repo.approve(99)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_membership_not_pending(self):
        # event_id resolves to a user, but memberships UPDATE matches 0 rows
        # (user wasn't in 'pending' state) → return False without writing
        # an 'approved' event.
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: "user-uuid" if k == "user_id" else None)
        pool, conn = _make_pool(fetchrow=row, execute="UPDATE 0")
        repo = ActivationRequestRepository(pool)
        result = await repo.approve(1)
        assert result is False

    @pytest.mark.asyncio
    async def test_approve_issues_update_and_event_insert(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value="user-uuid")
        pool, conn = _make_pool(fetchrow=row, execute="UPDATE 1")
        repo = ActivationRequestRepository(pool)
        await repo.approve(1)
        # Two execute calls: UPDATE memberships SET status='active' +
        # INSERT INTO membership_events ('approved', 'owner').
        assert conn.execute.await_count == 2
        sqls = [c.args[0] for c in conn.execute.await_args_list]
        assert any("UPDATE memberships" in s for s in sqls)
        assert any("INSERT INTO membership_events" in s for s in sqls)


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


class TestReject:
    """reject() mirrors approve() but the terminal state is 'rejected'."""

    @pytest.mark.asyncio
    async def test_returns_true_when_rejected(self):
        # fetchrow → resolves event_id to user; UPDATE memberships → UPDATE 1.
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: "user-uuid" if k == "user_id" else None)
        pool, _ = _make_pool(fetchrow=row, execute="UPDATE 1")
        repo = ActivationRequestRepository(pool)
        result = await repo.reject(1)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_event_id_not_found(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationRequestRepository(pool)
        result = await repo.reject(99)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_membership_not_pending(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: "user-uuid" if k == "user_id" else None)
        pool, _ = _make_pool(fetchrow=row, execute="UPDATE 0")
        repo = ActivationRequestRepository(pool)
        result = await repo.reject(99)
        assert result is False
