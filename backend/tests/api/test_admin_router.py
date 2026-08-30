"""Tests for api.routers.admin_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")
os.environ.setdefault("OWNER_ID", "owner-123")

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    get_admission_service,
    get_channel_service,
    get_current_channel_id,
    get_current_user_id,
    get_db_pool,
    get_twitch_api,
)
from core.error_handlers import register_exception_handlers
from routers.admin_router import router as _admin_router

OWNER_ID = "owner-123"
_APPROVER_UUID = "11111111-1111-1111-1111-111111111111"
_NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(
    channel_id: str = OWNER_ID,
    mock_twitch_api: MagicMock | None = None,
    mock_channel_service: MagicMock | None = None,
    mock_pool: MagicMock | None = None,
    mock_admission: MagicMock | None = None,
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_admin_router)
    app.dependency_overrides[get_current_channel_id] = lambda: channel_id
    # Owner-only endpoints that mutate via AdmissionService also need the
    # caller's user_id for actor_user_id attribution.
    app.dependency_overrides[get_current_user_id] = lambda: _APPROVER_UUID
    app.dependency_overrides[get_db_pool] = lambda: mock_pool or AsyncMock()
    if mock_twitch_api is not None:
        app.dependency_overrides[get_twitch_api] = lambda: mock_twitch_api
    if mock_channel_service is not None:
        app.dependency_overrides[get_channel_service] = lambda: mock_channel_service
    if mock_admission is not None:
        app.dependency_overrides[get_admission_service] = lambda: mock_admission
    return TestClient(app, raise_server_exceptions=False)


def _make_pool(*, fetchrow=None, fetch=None, fetchval=None, execute=None) -> MagicMock:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    conn.fetch.return_value = fetch or []
    conn.fetchval.return_value = fetchval
    conn.execute.return_value = execute or "DELETE 0"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    # Some endpoints call pool.fetch() / pool.fetchval() directly (not via acquire)
    pool.fetch = AsyncMock(return_value=fetch or [])
    pool.fetchval = AsyncMock(return_value=fetchval)
    return pool


# ── require_owner guard ──────────────────────────────────────────────────────


class TestRequireOwner:
    def test_non_owner_gets_403(self):
        r = _make_client(channel_id="not-the-owner").get("/api/admin/grants")
        assert r.status_code == 403

    def test_owner_passes_guard(self):
        r = _make_client(mock_pool=_make_pool(fetch=[])).get("/api/admin/grants")
        assert r.status_code == 200


# ── GET /api/admin/grants ──────────────────────────────────────────────────


_GRANT_ROW = {
    "id": 1,
    "kind": "channel_points",
    "status": "issued",
    "platform_user_id": "u1",
    "code_plain": "123456",
    "reward_cost": 500,
    "channel_id": "c1",
    "redemption_id": "r1",
    "issued_at": _NOW,
    "expires_at": _NOW,
    "used_at": None,
    "attempt_count": 0,
    "display_name": "Alice",
    "avatar": None,
    "username": "alice",
}


class TestListGrants:
    def test_returns_empty_list(self):
        r = _make_client(mock_pool=_make_pool(fetch=[])).get("/api/admin/grants")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_grants(self):
        r = _make_client(mock_pool=_make_pool(fetch=[_GRANT_ROW])).get("/api/admin/grants")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["kind"] == "channel_points"
        assert body[0]["id"] == 1


# ── POST /api/admin/grants ─────────────────────────────────────────────────


class TestCreateOwnerGrant:
    def test_issues_code(self):
        with patch("routers.admin_router.ActivationCodeRepository") as mock_repo:
            mock_repo.return_value.create_owner_code = AsyncMock(return_value="654321")
            r = _make_client().post("/api/admin/grants")
        assert r.status_code == 200
        assert r.json() == {"code": "654321"}


# ── DELETE /api/admin/grants/{grant_id} ────────────────────────────────────


class TestRevokeGrant:
    def test_revoke_existing(self):
        with patch("routers.admin_router.ActivationCodeRepository") as mock_repo:
            mock_repo.return_value.revoke = AsyncMock(return_value=True)
            r = _make_client().delete("/api/admin/grants/5")
        assert r.status_code == 200
        assert r.json()["revoked"] is True

    def test_revoke_missing_returns_404(self):
        with patch("routers.admin_router.ActivationCodeRepository") as mock_repo:
            mock_repo.return_value.revoke = AsyncMock(return_value=False)
            r = _make_client().delete("/api/admin/grants/999")
        assert r.status_code == 404


# ── GET /api/admin/onboarding-funnel ──────────────────────────────────────


class TestOnboardingFunnel:
    def test_returns_active_count_and_kind_breakdown(self):
        kind_row = {
            "kind": "channel_points",
            "issued_7d": 3,
            "consumed_7d": 2,
            "issued_30d": 10,
            "consumed_30d": 8,
            "issued_all": 20,
            "consumed_all": 15,
            "outstanding": 5,
        }
        pool = _make_pool(fetch=[kind_row], fetchval=42)
        r = _make_client(mock_pool=pool).get("/api/admin/onboarding-funnel")
        assert r.status_code == 200
        body = r.json()
        assert body["active_members"] == 42
        assert body["by_kind"][0]["consumed_all"] == 15


# ── GET /api/admin/activation-requests ──────────────────────────────────────


class TestGetActivationRequests:
    """Backed by memberships + membership_events; pool.fetch returns rows
    matching the ActivationRequestInfo shape."""

    def test_returns_empty_list(self):
        pool = _make_pool(fetch=[])
        # The endpoint uses pool.fetch (the asyncpg pool's direct fetch),
        # not pool.acquire().fetch — wire it explicitly.
        pool.fetch = AsyncMock(return_value=[])
        r = _make_client(mock_pool=pool).get("/api/admin/activation-requests")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_pending_memberships(self):
        pending = [
            {
                "id": "aaaa1111-2222-3333-4444-555555555555",
                "platform_user_id": "u1",
                "display_name": "Alice",
                "username": "alice",
                "avatar": None,
                "note": "please",
                "created_at": _NOW,
            }
        ]
        pool = _make_pool(fetch=pending)
        pool.fetch = AsyncMock(return_value=pending)
        r = _make_client(mock_pool=pool).get("/api/admin/activation-requests")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["id"] == "aaaa1111-2222-3333-4444-555555555555"
        assert body[0]["platform_user_id"] == "u1"


# ── POST /api/admin/activation-requests/{user_id}/approve ───────────────────


class TestApproveActivationRequest:
    """Now delegates to AdmissionService.approve; takes user_id (UUID) not int."""

    def _decision(self):
        membership = MagicMock(status="active")
        return MagicMock(membership=membership, event_id=11, state_changed=True)

    def test_approve_returns_approved_true(self):
        admission = MagicMock()
        admission.approve = AsyncMock(return_value=self._decision())
        target_user = "bbbb2222-3333-4444-5555-666666666666"
        r = _make_client(mock_admission=admission).post(
            f"/api/admin/activation-requests/{target_user}/approve",
            json={"reason": "vetted"},
        )
        assert r.status_code == 200
        assert r.json()["approved"] is True
        # AdmissionService.approve was called with the target user + approver
        admission.approve.assert_awaited_once()
        kwargs = admission.approve.call_args.kwargs
        assert kwargs["user_id"] == target_user
        assert kwargs["approver_user_id"] == _APPROVER_UUID
        assert kwargs["reason"] == "vetted"

    def test_approve_no_body_uses_default_reason(self):
        admission = MagicMock()
        admission.approve = AsyncMock(return_value=self._decision())
        r = _make_client(mock_admission=admission).post(
            "/api/admin/activation-requests/bbbb2222-3333-4444-5555-666666666666/approve",
        )
        assert r.status_code == 200
        assert admission.approve.call_args.kwargs["reason"] == "admin_approval"

    def test_approve_missing_membership_returns_404(self):
        admission = MagicMock()
        admission.approve = AsyncMock(side_effect=ValueError("No membership"))
        r = _make_client(mock_admission=admission).post(
            "/api/admin/activation-requests/cccc3333-4444-5555-6666-777777777777/approve",
            json={"reason": "x"},
        )
        assert r.status_code == 404


# ── POST /api/admin/activation-requests/{user_id}/reject ────────────────────


class TestRejectActivationRequest:
    def _decision(self):
        membership = MagicMock(status="rejected")
        return MagicMock(membership=membership, event_id=5, state_changed=True)

    def test_reject_returns_rejected_true(self):
        admission = MagicMock()
        admission.reject = AsyncMock(return_value=self._decision())
        target_user = "dddd4444-5555-6666-7777-888888888888"
        r = _make_client(mock_admission=admission).post(
            f"/api/admin/activation-requests/{target_user}/reject",
            json={"reason": "bad_actor"},
        )
        assert r.status_code == 200
        assert r.json()["rejected"] is True
        kwargs = admission.reject.call_args.kwargs
        assert kwargs["user_id"] == target_user
        assert kwargs["approver_user_id"] == _APPROVER_UUID
        assert kwargs["reason"] == "bad_actor"

    def test_reject_missing_membership_returns_404(self):
        admission = MagicMock()
        admission.reject = AsyncMock(side_effect=ValueError("No membership"))
        r = _make_client(mock_admission=admission).post(
            "/api/admin/activation-requests/eeee5555-6666-7777-8888-999999999999/reject",
            json={"reason": "x"},
        )
        assert r.status_code == 404


# ── GET /api/admin/memberships/{user_id}/timeline ───────────────────────────


class TestGetMembershipTimeline:
    def test_timeline_returns_events(self):
        # admin_router does ``MembershipEventInfo(**event.__dict__)``, so each
        # mocked event needs a real ``__dict__`` that maps to the response
        # model's fields. SimpleNamespace gives us that without the magic
        # collisions MagicMock causes when ``__dict__`` is set via kwargs.
        events = [
            SimpleNamespace(
                id=1,
                event_type="requested",
                actor_type="system",
                actor_user_id=None,
                reason="first_signup",
                metadata={},
                occurred_at=_NOW,
            ),
            SimpleNamespace(
                id=2,
                event_type="approved",
                actor_type="owner",
                actor_user_id=_APPROVER_UUID,
                reason="vetted",
                metadata={},
                occurred_at=_NOW,
            ),
        ]
        admission = MagicMock()
        admission.timeline = AsyncMock(return_value=events)
        r = _make_client(mock_admission=admission).get(
            "/api/admin/memberships/ffff6666-7777-8888-9999-aaaaaaaaaaaa/timeline",
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 2
        assert body[0]["event_type"] == "requested"
        assert body[1]["actor_type"] == "owner"


# ── POST /api/admin/memberships/{user_id}/suspend ───────────────────────────


class TestSuspendMembership:
    def _decision(self):
        membership = MagicMock(status="suspended")
        return MagicMock(membership=membership, event_id=21, state_changed=True)

    def test_suspend_returns_true(self):
        admission = MagicMock()
        admission.suspend = AsyncMock(return_value=self._decision())
        target_user = "dddd4444-5555-6666-7777-888888888888"
        r = _make_client(mock_admission=admission).post(
            f"/api/admin/memberships/{target_user}/suspend",
            json={"reason": "abuse"},
        )
        assert r.status_code == 200
        assert r.json()["suspended"] is True
        kwargs = admission.suspend.call_args.kwargs
        assert kwargs["user_id"] == target_user
        assert kwargs["approver_user_id"] == _APPROVER_UUID
        assert kwargs["reason"] == "abuse"

    def test_suspend_missing_membership_returns_404(self):
        admission = MagicMock()
        admission.suspend = AsyncMock(side_effect=ValueError("No membership"))
        r = _make_client(mock_admission=admission).post(
            "/api/admin/memberships/eeee5555-6666-7777-8888-999999999999/suspend",
            json={"reason": "abuse"},
        )
        assert r.status_code == 404

    def test_suspend_missing_reason_returns_400(self):
        admission = MagicMock()
        r = _make_client(mock_admission=admission).post(
            "/api/admin/memberships/dddd4444-5555-6666-7777-888888888888/suspend",
            json={"reason": ""},
        )
        assert r.status_code == 400

    def test_suspend_whitespace_reason_returns_400(self):
        admission = MagicMock()
        r = _make_client(mock_admission=admission).post(
            "/api/admin/memberships/dddd4444-5555-6666-7777-888888888888/suspend",
            json={"reason": "   "},
        )
        assert r.status_code == 400
        admission.suspend.assert_not_called()

    def test_suspend_trims_reason_before_recording(self):
        admission = MagicMock()
        admission.suspend = AsyncMock(return_value=self._decision())
        r = _make_client(mock_admission=admission).post(
            "/api/admin/memberships/dddd4444-5555-6666-7777-888888888888/suspend",
            json={"reason": "  abuse  "},
        )
        assert r.status_code == 200
        assert admission.suspend.call_args.kwargs["reason"] == "abuse"

    def test_suspend_rejects_reason_over_500_characters(self):
        admission = MagicMock()
        r = _make_client(mock_admission=admission).post(
            "/api/admin/memberships/dddd4444-5555-6666-7777-888888888888/suspend",
            json={"reason": "x" * 501},
        )
        assert r.status_code == 422
        admission.suspend.assert_not_called()


# ── POST /api/admin/memberships/{user_id}/reinstate ─────────────────────────


class TestReinstateMembership:
    def _decision(self):
        membership = MagicMock(status="active")
        return MagicMock(membership=membership, event_id=22, state_changed=True)

    def test_reinstate_returns_true(self):
        admission = MagicMock()
        admission.reinstate = AsyncMock(return_value=self._decision())
        target_user = "dddd4444-5555-6666-7777-888888888888"
        r = _make_client(mock_admission=admission).post(
            f"/api/admin/memberships/{target_user}/reinstate",
            json={"reason": "appeal"},
        )
        assert r.status_code == 200
        assert r.json()["reinstated"] is True
        kwargs = admission.reinstate.call_args.kwargs
        assert kwargs["user_id"] == target_user
        assert kwargs["approver_user_id"] == _APPROVER_UUID
        assert kwargs["reason"] == "appeal"

    def test_reinstate_missing_membership_returns_404(self):
        admission = MagicMock()
        admission.reinstate = AsyncMock(side_effect=ValueError("No membership"))
        r = _make_client(mock_admission=admission).post(
            "/api/admin/memberships/eeee5555-6666-7777-8888-999999999999/reinstate",
            json={"reason": "appeal"},
        )
        assert r.status_code == 404


# ── /api/admin/modules/ai-packs ──────────────────────────────────────────────


class TestModuleAiPacks:
    def test_get_returns_enabled_packs(self):
        with patch("routers.admin.modules.ModuleConfigRepository") as mc:
            mc.return_value.get_enabled_packs = AsyncMock(return_value=["lol", "valorant"])
            r = _make_client().get("/api/admin/modules/ai-packs")
        assert r.status_code == 200
        assert r.json() == ["lol", "valorant"]

    def test_patch_sets_packs_and_notifies(self):
        conn = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        with patch("routers.admin.modules.ModuleConfigRepository") as mc:
            mc.return_value.set_enabled_packs = AsyncMock(return_value=["lol"])
            r = _make_client(mock_pool=pool).patch(
                "/api/admin/modules/ai-packs", json={"enabled_packs": ["lol"]}
            )
        assert r.status_code == 200
        assert r.json() == ["lol"]
        conn.execute.assert_awaited_once()

    def test_non_owner_gets_403(self):
        r = _make_client(channel_id="not-the-owner").get("/api/admin/modules/ai-packs")
        assert r.status_code == 403


# ── POST /api/admin/db/query ─────────────────────────────────────────────────


class TestRunDbQuery:
    def _make_conn(self, rows=None):
        conn = AsyncMock()
        conn.fetch.return_value = rows or []
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=None)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=mock_tx)
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool, conn

    def test_select_returns_results(self):
        row = MagicMock()
        row.keys.return_value = ["id", "name"]
        row.__iter__ = MagicMock(return_value=iter([1, "alice"]))
        # Use a real-looking asyncpg row
        pool, conn = self._make_conn(rows=[{"id": 1, "name": "alice"}])
        # Patch fetch to return a row with .keys()
        mock_row = MagicMock()
        mock_row.keys.return_value = ["id", "name"]
        mock_row.__iter__ = MagicMock(return_value=iter([1, "alice"]))
        conn.fetch.return_value = [mock_row]
        r = _make_client(mock_pool=pool).post("/api/admin/db/query", json={"sql": "SELECT 1"})
        assert r.status_code == 200
        data = r.json()
        assert data["row_count"] == 1
        assert data["columns"] == ["id", "name"]

    def test_non_select_rejected(self):
        r = _make_client().post("/api/admin/db/query", json={"sql": "DELETE FROM users"})
        assert r.status_code == 400
        assert "SELECT" in r.json()["detail"]

    def test_empty_result_returns_zero_rows(self):
        pool, conn = self._make_conn(rows=[])
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT 1 WHERE FALSE"}
        )
        assert r.status_code == 200
        assert r.json()["row_count"] == 0

    def test_with_clause_is_allowed(self):
        pool, conn = self._make_conn(rows=[])
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query",
            json={"sql": "WITH cte AS (SELECT 1) SELECT * FROM cte"},
        )
        assert r.status_code == 200

    def test_db_exception_returns_400(self):
        pool, conn = self._make_conn()
        conn.fetch.side_effect = Exception("syntax error")
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT bad syntax$$"}
        )
        assert r.status_code == 400

    def test_query_wrapped_in_subquery_with_cap(self):
        """The router wraps the query in `SELECT * FROM (...) LIMIT cap+1`."""
        pool, conn = self._make_conn(rows=[])
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT id FROM channels"}
        )
        assert r.status_code == 200
        sent = conn.fetch.call_args[0][0]
        assert sent.startswith("SELECT * FROM (")
        assert "LIMIT 501" in sent

    def test_sets_console_role_and_statement_timeout(self):
        pool, conn = self._make_conn(rows=[])
        _make_client(mock_pool=pool).post("/api/admin/db/query", json={"sql": "SELECT 1"})
        executed = [c.args[0] for c in conn.execute.call_args_list]
        assert any("SET LOCAL ROLE niibot_db_console" in s for s in executed)
        assert any("statement_timeout" in s for s in executed)

    def test_multi_statement_rejected(self):
        r = _make_client().post("/api/admin/db/query", json={"sql": "SELECT 1; DROP TABLE users"})
        assert r.status_code == 400

    def test_trailing_semicolon_is_allowed(self):
        pool, conn = self._make_conn(rows=[])
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT 1 FROM channels;  "}
        )
        assert r.status_code == 200

    def test_console_role_missing_returns_clear_error(self):
        import asyncpg

        pool, conn = self._make_conn(rows=[])

        def _execute(stmt, *a, **kw):
            if "SET LOCAL ROLE" in stmt:
                raise asyncpg.exceptions.UndefinedObjectError("role does not exist")
            return "SET"

        conn.execute.side_effect = _execute
        r = _make_client(mock_pool=pool).post("/api/admin/db/query", json={"sql": "SELECT 1"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ADMIN.DB_CONSOLE_UNAVAILABLE"

    def test_insufficient_privilege_returns_protected_message(self):
        import asyncpg

        pool, conn = self._make_conn()
        conn.fetch.side_effect = asyncpg.exceptions.InsufficientPrivilegeError(
            "permission denied for table tokens"
        )
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT token FROM tokens"}
        )
        assert r.status_code == 400
        assert "permission denied" not in r.text

    def test_truncated_when_over_cap(self):
        rows = []
        for _ in range(501):
            mr = MagicMock()
            mr.keys.return_value = ["id"]
            mr.__iter__ = MagicMock(return_value=iter([1]))
            rows.append(mr)
        pool, conn = self._make_conn()
        conn.fetch.return_value = rows
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT id FROM stream_events"}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["truncated"] is True
        assert data["row_count"] == 500

    def test_query_is_audit_logged(self, caplog):
        import logging

        pool, conn = self._make_conn(rows=[])
        with caplog.at_level(logging.INFO):
            _make_client(mock_pool=pool).post("/api/admin/db/query", json={"sql": "SELECT 1"})
        assert "db_console_query" in caplog.text

    def test_timeout_returns_408(self):
        pool, conn = self._make_conn()
        conn.fetch.side_effect = TimeoutError("query timed out")
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query",
            json={"sql": "SELECT id FROM channels LIMIT 10"},
        )
        assert r.status_code == 408

    def test_query_canceled_returns_408(self):
        import asyncpg

        pool, conn = self._make_conn()
        conn.fetch.side_effect = asyncpg.exceptions.QueryCanceledError("canceled")
        r = _make_client(mock_pool=pool).post(
            "/api/admin/db/query", json={"sql": "SELECT pg_sleep(10)"}
        )
        assert r.status_code == 408


# ── GET /api/admin/db/schema ────────────────────────────────────────────────


class TestDbSchema:
    def _make_pool_with_rows(self, rows, probe=None):
        conn = AsyncMock()
        # 1st fetch = catalog rows; 2nd fetch = the batched EXISTS probe.
        conn.fetch.side_effect = [rows, probe if probe is not None else []]
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=None)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=mock_tx)
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool

    def test_non_owner_gets_403(self):
        r = _make_client(channel_id="not-the-owner").get("/api/admin/db/schema")
        assert r.status_code == 403

    @staticmethod
    def _col(table, relkind, name, dtype, approx, can_select=True):
        return {
            "table_name": table,
            "relkind": relkind,
            "column_name": name,
            "data_type": dtype,
            "approx_rows": approx,
            "can_select": can_select,
        }

    def test_groups_columns_by_table(self):
        rows = [
            self._col("channels", "r", "channel_id", "text", 12),
            self._col("channels", "r", "enabled", "boolean", 12),
            self._col("v_session_summary", "v", "session_id", "integer", None),
        ]
        pool = self._make_pool_with_rows(rows)
        r = _make_client(mock_pool=pool).get("/api/admin/db/schema")
        assert r.status_code == 200
        data = r.json()
        assert [t["name"] for t in data] == ["channels", "v_session_summary"]
        assert data[0]["kind"] == "table"
        assert data[0]["approx_rows"] == 12
        assert len(data[0]["columns"]) == 2
        assert data[0]["has_hidden_columns"] is False
        assert data[1]["kind"] == "view"

    def test_hidden_columns_are_dropped_and_flagged(self):
        rows = [
            self._col("tokens", "r", "user_id", "text", 9),
            self._col("tokens", "r", "token", "text", 9, can_select=False),
            self._col("tokens", "r", "refresh", "text", 9, can_select=False),
        ]
        pool = self._make_pool_with_rows(rows)
        r = _make_client(mock_pool=pool).get("/api/admin/db/schema")
        data = r.json()
        assert len(data) == 1
        assert [c["name"] for c in data[0]["columns"]] == ["user_id"]
        assert data[0]["has_hidden_columns"] is True

    def test_fully_protected_table_is_omitted(self):
        rows = [self._col("secret", "r", "k", "text", 1, can_select=False)]
        pool = self._make_pool_with_rows(rows)
        r = _make_client(mock_pool=pool).get("/api/admin/db/schema")
        assert r.json() == []

    def test_empty_tables_flagged_from_probe(self):
        rows = [
            self._col("channels", "r", "id", "text", 8),
            self._col("game_queue_entries", "r", "id", "text", 0),
        ]
        probe = [{"idx": 0, "has_rows": True}, {"idx": 1, "has_rows": False}]
        pool = self._make_pool_with_rows(rows, probe=probe)
        data = _make_client(mock_pool=pool).get("/api/admin/db/schema").json()
        by = {t["name"]: t for t in data}
        assert by["channels"]["is_empty"] is False
        assert by["game_queue_entries"]["is_empty"] is True

    def test_empty_probe_failure_is_non_fatal(self):
        import asyncpg

        rows = [self._col("channels", "r", "id", "text", 8)]
        conn = AsyncMock()
        conn.fetch.side_effect = [rows, asyncpg.exceptions.QueryCanceledError("slow")]
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=None)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=mock_tx)
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        r = _make_client(mock_pool=pool).get("/api/admin/db/schema")
        assert r.status_code == 200
        assert r.json()[0]["is_empty"] is False

    def test_missing_console_role_returns_clear_error(self):
        import asyncpg

        conn = AsyncMock()
        conn.fetch.side_effect = asyncpg.exceptions.UndefinedObjectError("no role")
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        r = _make_client(mock_pool=pool).get("/api/admin/db/schema")
        assert r.status_code == 400


# ── _parse_docker_stream ────────────────────────────────────────────────────


class TestParseDockerStream:
    def test_parses_stdout_line(self):
        import struct

        from routers.admin_router import _parse_docker_stream

        payload = b"hello world\n"
        header = bytes([1, 0, 0, 0]) + struct.pack(">I", len(payload))
        raw = header + payload
        lines = _parse_docker_stream(raw)

        assert len(lines) == 1
        assert lines[0].stream == "stdout"
        assert lines[0].text == "hello world"

    def test_parses_stderr_line(self):
        import struct

        from routers.admin_router import _parse_docker_stream

        payload = b"error occurred\n"
        header = bytes([2, 0, 0, 0]) + struct.pack(">I", len(payload))
        raw = header + payload
        lines = _parse_docker_stream(raw)

        assert len(lines) == 1
        assert lines[0].stream == "stderr"

    def test_empty_bytes_returns_empty(self):
        from routers.admin_router import _parse_docker_stream

        assert _parse_docker_stream(b"") == []

    def test_multi_line_payload(self):
        import struct

        from routers.admin_router import _parse_docker_stream

        payload = b"line1\nline2\nline3\n"
        header = bytes([1, 0, 0, 0]) + struct.pack(">I", len(payload))
        lines = _parse_docker_stream(header + payload)

        assert len(lines) == 3
        assert lines[0].text == "line1"
        assert lines[2].text == "line3"

    def test_incomplete_frame_is_skipped(self):
        from routers.admin_router import _parse_docker_stream

        # Only 4 bytes — not enough for a complete 8-byte header
        lines = _parse_docker_stream(b"\x01\x00\x00\x00")
        assert lines == []


# ── _json_safe ──────────────────────────────────────────────────────────────


class TestJsonSafe:
    def test_none_passthrough(self):
        from routers.admin_router import _json_safe

        assert _json_safe(None) is None

    def test_bool_passthrough(self):
        from routers.admin_router import _json_safe

        assert _json_safe(True) is True

    def test_int_passthrough(self):
        from routers.admin_router import _json_safe

        assert _json_safe(42) == 42

    def test_float_passthrough(self):
        from routers.admin_router import _json_safe

        assert _json_safe(3.14) == 3.14

    def test_str_passthrough(self):
        from routers.admin_router import _json_safe

        assert _json_safe("hello") == "hello"

    def test_datetime_serialised_to_iso(self):
        from datetime import UTC, datetime

        from routers.admin_router import _json_safe

        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = _json_safe(dt)
        assert "2024-01-15" in result

    def test_decimal_converts_to_float(self):
        import decimal

        from routers.admin_router import _json_safe

        assert _json_safe(decimal.Decimal("3.14")) == pytest.approx(3.14)

    def test_uuid_converts_to_str(self):
        import uuid

        from routers.admin_router import _json_safe

        u = uuid.uuid4()
        result = _json_safe(u)
        assert isinstance(result, str)
        assert str(u) == result

    def test_unknown_type_converts_to_str(self):
        from routers.admin_router import _json_safe

        class Weird:
            def __str__(self):
                return "weird"

        assert _json_safe(Weird()) == "weird"


# ── _scope_diff ─────────────────────────────────────────────────────────────


class TestScopeDiff:
    def test_empty_stored_all_missing(self):
        from routers.admin_router import _scope_diff

        granted, missing = _scope_diff(None, ["a", "b", "c"])
        assert granted == []
        assert missing == ["a", "b", "c"]

    def test_all_scopes_present(self):
        from routers.admin_router import _scope_diff

        granted, missing = _scope_diff("a b c", ["a", "b", "c"])
        assert granted == ["a", "b", "c"]
        assert missing == []

    def test_partial_scopes(self):
        from routers.admin_router import _scope_diff

        granted, missing = _scope_diff("a c", ["a", "b", "c"])
        assert "a" in granted
        assert "c" in granted
        assert "b" in missing

    def test_empty_required_returns_empty_lists(self):
        from routers.admin_router import _scope_diff

        granted, missing = _scope_diff("a b c", [])
        assert granted == []
        assert missing == []


# ── GET /api/admin/bot-status ────────────────────────────────────────────────


class TestGetBotStatus:
    def test_no_bot_id_returns_404(self):
        with patch("routers.admin_router.get_settings") as mock_settings:
            mock_settings.return_value.bot_id = ""
            mock_settings.return_value.owner_id = OWNER_ID
            r = _make_client().get("/api/admin/bot-status")
        assert r.status_code == 404

    def test_no_token_returns_no_token_status(self):
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[
                {
                    "login": "niibot",
                    "display_name": "Niibot",
                    "profile_image_url": "https://img.example.com/bot.png",
                }
            ]
        )
        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(mock_twitch_api=mock_twitch).get("/api/admin/bot-status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "no_token"
        assert data["granted_scopes"] == []

    def test_all_scopes_granted_returns_ok_status(self):
        from shared.twitch_scopes import BOT_SCOPES

        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[{"login": "niibot", "display_name": "Niibot", "profile_image_url": ""}]
        )
        token_obj = MagicMock()
        token_obj.scopes = " ".join(BOT_SCOPES)
        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch).get("/api/admin/bot-status")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["missing_scopes"] == []

    def test_missing_some_scopes_returns_missing_status(self):
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[{"login": "niibot", "display_name": "Niibot", "profile_image_url": ""}]
        )
        token_obj = MagicMock()
        token_obj.scopes = "chat:read"  # only one scope
        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch).get("/api/admin/bot-status")
        assert r.status_code == 200
        assert r.json()["status"] == "missing"
        assert len(r.json()["missing_scopes"]) > 0


# ── GET /api/admin/channels ──────────────────────────────────────────────────


class TestGetAdminChannels:
    def _make_channel(self, channel_id: str, enabled: bool = True):
        from shared.models.channel import Channel

        return Channel(channel_id=channel_id, channel_name=channel_id, enabled=enabled)

    def _make_twitch_user(self, channel_id: str, login: str, display_name: str) -> dict:
        return {
            "id": channel_id,
            "login": login,
            "display_name": display_name,
            "profile_image_url": "",
            "offline_image_url": "",
        }

    def test_returns_empty_when_no_other_channels(self):
        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[self._make_channel(OWNER_ID)]
            )
            cr.return_value.list_monitored_owner_channel_status = AsyncMock(return_value={})
            r = _make_client().get("/api/admin/channels")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_enabled_channel_with_is_enabled_true(self):
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[self._make_twitch_user("ch-other", "other", "Other")]
        )
        mock_twitch.get_streams = AsyncMock(return_value=[])
        mock_twitch.get_bot_mod_status = AsyncMock(return_value="mod")

        mock_cs = MagicMock()
        mock_cs.get_token_with_refresh = AsyncMock(return_value="tok")

        token_obj = MagicMock()
        token_obj.scopes = ""

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[
                    self._make_channel(OWNER_ID),
                    self._make_channel("ch-other", enabled=True),
                ]
            )
            cr.return_value.list_monitored_owner_channel_status = AsyncMock(
                return_value={"ch-other": ("active", "user-other", None)}
            )
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch, mock_channel_service=mock_cs).get(
                "/api/admin/channels"
            )

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "other"
        assert data[0]["is_enabled"] is True
        assert data[0]["membership_status"] == "active"
        assert data[0]["owner_user_id"] == "user-other"

    def test_returns_paused_channel_with_is_enabled_false(self):
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[self._make_twitch_user("ch-paused", "paused", "Paused")]
        )
        mock_twitch.get_streams = AsyncMock(return_value=[])
        mock_twitch.get_bot_mod_status = AsyncMock(return_value="mod")

        mock_cs = MagicMock()
        mock_cs.get_token_with_refresh = AsyncMock(return_value="tok")

        token_obj = MagicMock()
        token_obj.scopes = ""

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[
                    self._make_channel(OWNER_ID),
                    self._make_channel("ch-paused", enabled=False),
                ]
            )
            # Active owner who manually paused the bot: still an admitted tenant,
            # so it must appear (filter is by membership, not by enabled).
            cr.return_value.list_monitored_owner_channel_status = AsyncMock(
                return_value={"ch-paused": ("active", "user-paused", None)}
            )
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch, mock_channel_service=mock_cs).get(
                "/api/admin/channels"
            )

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "paused"
        assert data[0]["is_enabled"] is False
        assert data[0]["membership_status"] == "active"

    def test_excludes_rejected_owner_channel(self):
        # A channel whose owner was rejected has no monitoring value and must
        # not appear — it's absent from list_monitored_owner_channel_status
        # (which only returns active/pending/suspended).
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[self._make_twitch_user("ch-rejected", "rejected", "Rejected")]
        )
        mock_twitch.get_streams = AsyncMock(return_value=[])
        mock_twitch.get_bot_mod_status = AsyncMock(return_value="mod")

        mock_cs = MagicMock()
        mock_cs.get_token_with_refresh = AsyncMock(return_value="tok")

        token_obj = MagicMock()
        token_obj.scopes = ""

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[
                    self._make_channel(OWNER_ID),
                    self._make_channel("ch-rejected", enabled=False),
                ]
            )
            cr.return_value.list_monitored_owner_channel_status = AsyncMock(return_value={})
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch, mock_channel_service=mock_cs).get(
                "/api/admin/channels"
            )

        assert r.status_code == 200
        assert r.json() == []

    def test_includes_pending_owner_channel(self):
        # Pending owners now surface in the monitor grid (待審 bucket in the
        # frontend) instead of being dropped entirely — they already have a
        # channels row from the OAuth callback.
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[self._make_twitch_user("ch-pending", "pending", "Pending")]
        )
        mock_twitch.get_streams = AsyncMock(return_value=[])
        mock_twitch.get_bot_mod_status = AsyncMock(return_value="mod")

        mock_cs = MagicMock()
        mock_cs.get_token_with_refresh = AsyncMock(return_value="tok")

        token_obj = MagicMock()
        token_obj.scopes = ""

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[
                    self._make_channel(OWNER_ID),
                    self._make_channel("ch-pending", enabled=False),
                ]
            )
            cr.return_value.list_monitored_owner_channel_status = AsyncMock(
                return_value={"ch-pending": ("pending", "user-pending", "awaiting_review")}
            )
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch, mock_channel_service=mock_cs).get(
                "/api/admin/channels"
            )

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "pending"
        assert data[0]["membership_status"] == "pending"
        assert data[0]["owner_user_id"] == "user-pending"

    def test_includes_suspended_owner_channel(self):
        # Suspended owners surface too (已停權 bucket in the frontend), with
        # owner_user_id populated so the frontend can call the reinstate
        # endpoint, which is keyed on user_id.
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[self._make_twitch_user("ch-suspended", "suspended", "Suspended")]
        )
        mock_twitch.get_streams = AsyncMock(return_value=[])
        mock_twitch.get_bot_mod_status = AsyncMock(return_value="mod")

        mock_cs = MagicMock()
        mock_cs.get_token_with_refresh = AsyncMock(return_value="tok")

        token_obj = MagicMock()
        token_obj.scopes = ""

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[
                    self._make_channel(OWNER_ID),
                    self._make_channel("ch-suspended", enabled=False),
                ]
            )
            cr.return_value.list_monitored_owner_channel_status = AsyncMock(
                return_value={"ch-suspended": ("suspended", "user-suspended", "abuse")}
            )
            cr.return_value.get_token = AsyncMock(return_value=token_obj)
            r = _make_client(mock_twitch_api=mock_twitch, mock_channel_service=mock_cs).get(
                "/api/admin/channels"
            )

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "suspended"
        assert data[0]["membership_status"] == "suspended"
        assert data[0]["membership_reason"] == "abuse"
        assert data[0]["owner_user_id"] == "user-suspended"


# ── GET /api/admin/logs/containers ──────────────────────────────────────────


class TestListLogContainers:
    def test_docker_unavailable_returns_all_not_running(self):
        with patch("routers.admin.logs.aiohttp.UnixConnector", side_effect=Exception("no socket")):
            r = _make_client().get("/api/admin/logs/containers")
        assert r.status_code == 200
        data = r.json()
        assert all(c["running"] is False for c in data)
        assert len(data) == 5  # api, twitch, discord, pg, instafix

    def test_dev_environment_uses_bare_container_names(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        with patch("routers.admin.logs.aiohttp.UnixConnector", side_effect=Exception("no socket")):
            r = _make_client().get("/api/admin/logs/containers")
        names = [c["name"] for c in r.json()]
        assert "nb-api" in names
        assert "nb-api-stg" not in names

    def test_staging_environment_uses_stg_suffix(self, monkeypatch):
        """Staging API shares the docker host with prod, so it must NOT query
        bare names — those would return prod container status."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        get_settings.cache_clear()
        with patch("routers.admin.logs.aiohttp.UnixConnector", side_effect=Exception("no socket")):
            r = _make_client().get("/api/admin/logs/containers")
        names = [c["name"] for c in r.json()]
        assert "nb-api-stg" in names
        assert "nb-api" not in names


# ── GET /api/admin/logs/{container} ─────────────────────────────────────────


class TestGetContainerLogs:
    def test_unknown_container_returns_400(self):
        r = _make_client().get("/api/admin/logs/unknown-container")
        assert r.status_code == 400
        assert "Unknown container" in r.json()["detail"]

    def test_docker_socket_unavailable_returns_503(self):
        with patch(
            "routers.admin.logs.aiohttp.UnixConnector",
            side_effect=Exception("no socket"),
        ):
            r = _make_client().get("/api/admin/logs/nb-api")
        assert r.status_code == 503

    def test_staging_rejects_prod_container_name(self, monkeypatch):
        """In staging, querying bare 'nb-api' must 400 — it's not in the allow list."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        get_settings.cache_clear()
        r = _make_client().get("/api/admin/logs/nb-api")
        assert r.status_code == 400


# ── GET /api/admin/bot-emotes ────────────────────────────────────────────────


def _channel(channel_id: str, enabled: bool = True):
    from shared.models.channel import Channel

    return Channel(channel_id=channel_id, channel_name=channel_id, enabled=enabled)


def _emote(eid: str, name: str, emote_type: str = "follower") -> dict:
    return {
        "id": eid,
        "name": name,
        "url": f"https://cdn.example.com/{eid}.png",
        "emote_type": emote_type,
        "tier": "",
        "animated": False,
    }


class TestGetBotEmotes:
    def test_non_owner_gets_403(self):
        r = _make_client(channel_id="someone-else").get("/api/admin/bot-emotes")
        assert r.status_code == 403

    def test_returns_empty_when_no_enabled_channels(self):
        # Only the bot's own channel and a disabled channel → nothing to aggregate.
        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[_channel("bot-test"), _channel("ch-off", enabled=False)]
            )
            cr.return_value.get_token = AsyncMock(return_value=MagicMock(token="tok"))
            r = _make_client().get("/api/admin/bot-emotes")
        assert r.status_code == 200
        assert r.json() == []

    def test_includes_owner_channel(self):
        # The owner is also a broadcaster; their own channel must be aggregated.
        # Only the bot's own channel is excluded.
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[
                {
                    "id": OWNER_ID,
                    "login": "owner",
                    "display_name": "Owner",
                    "profile_image_url": "https://img/o.png",
                },
                {
                    "id": "ch-a",
                    "login": "alice",
                    "display_name": "Alice",
                    "profile_image_url": "https://img/a.png",
                },
            ]
        )
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[_emote("e1", "follow1", "follower")]
        )
        mock_twitch.get_user_emotes = AsyncMock(return_value=[{"id": "e1"}])
        mock_twitch.is_user_subscribed = AsyncMock(return_value=False)

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[_channel(OWNER_ID), _channel("ch-a"), _channel("bot-test")]
            )
            cr.return_value.get_token = AsyncMock(return_value=MagicMock(token="tok"))
            r = _make_client(mock_twitch_api=mock_twitch).get("/api/admin/bot-emotes")

        assert r.status_code == 200
        ids = {c["channel_id"] for c in r.json()}
        assert ids == {OWNER_ID, "ch-a"}

    def test_aggregates_availability_per_channel(self):
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[
                {
                    "id": "ch-a",
                    "login": "alice",
                    "display_name": "Alice",
                    "profile_image_url": "https://img/a.png",
                }
            ]
        )
        # Channel has a follower emote and a subscription emote.
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[
                _emote("e1", "aliceFollow", "follower"),
                _emote("e2", "aliceSub", "subscriptions"),
            ]
        )
        # Bot can only access the follower emote (e1).
        mock_twitch.get_user_emotes = AsyncMock(return_value=[{"id": "e1"}])
        mock_twitch.is_user_subscribed = AsyncMock(return_value=False)

        with patch("routers.admin_router.ChannelRepository") as cr:
            # bot-test is the bot's own channel and must be excluded.
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[_channel("bot-test"), _channel("ch-a")]
            )
            cr.return_value.get_token = AsyncMock(return_value=MagicMock(token="tok"))
            r = _make_client(mock_twitch_api=mock_twitch).get("/api/admin/bot-emotes")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        ch = data[0]
        assert ch["channel_id"] == "ch-a"
        assert ch["display_name"] == "Alice"
        assert ch["total_count"] == 2
        assert ch["available_count"] == 1
        by_name = {e["name"]: e["available"] for e in ch["emotes"]}
        assert by_name == {"aliceFollow": True, "aliceSub": False}
        # Bot only has a follower emote here → not subscribed.
        assert ch["is_subscribed"] is False

    def test_reports_bot_subscription(self):
        # A real subscription is reported from the authoritative check, not
        # inferred from emote availability (which channel points could inflate).
        mock_twitch = MagicMock()
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[
                {
                    "id": "ch-a",
                    "login": "alice",
                    "display_name": "Alice",
                    "profile_image_url": "https://img/a.png",
                }
            ]
        )
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[_emote("e1", "aliceFollow", "follower")]
        )
        mock_twitch.get_user_emotes = AsyncMock(return_value=[{"id": "e1"}])
        mock_twitch.is_user_subscribed = AsyncMock(return_value=True)

        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(return_value=[_channel("ch-a")])
            cr.return_value.get_token = AsyncMock(return_value=MagicMock(token="tok"))
            r = _make_client(mock_twitch_api=mock_twitch).get("/api/admin/bot-emotes")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["is_subscribed"] is True
        mock_twitch.is_user_subscribed.assert_awaited_once_with("ch-a", "tok", "bot-test")


# ── POST /api/admin/bot-emotes/resync ────────────────────────────────────────


class TestResyncBotEmotes:
    def test_non_owner_gets_403(self):
        r = _make_client(channel_id="someone-else").post("/api/admin/bot-emotes/resync")
        assert r.status_code == 403

    def test_unknown_channel_returns_404(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[])
        with patch("routers.admin_router.ChannelRepository") as cr:
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[_channel(OWNER_ID), _channel("ch-a")]
            )
            cr.return_value.get_token = AsyncMock(return_value=MagicMock(token="tok"))
            r = _make_client(mock_twitch_api=mock_twitch).post(
                "/api/admin/bot-emotes/resync?channel_id=ch-missing"
            )
        assert r.status_code == 404

    def test_resync_writes_back_available_names(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[_emote("g1", "Kappa", "globals")])
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[
                _emote("e1", "aliceFollow", "follower"),
                _emote("e2", "aliceSub", "subscriptions"),
            ]
        )
        mock_twitch.get_user_emotes = AsyncMock(return_value=[{"id": "e1"}])

        with (
            patch("routers.admin_router.ChannelRepository") as cr,
            patch("routers.admin_router.sync_enabled_emotes", new_callable=AsyncMock) as mock_sync,
        ):
            cr.return_value.list_all_channels = AsyncMock(
                return_value=[_channel(OWNER_ID), _channel("ch-a")]
            )
            cr.return_value.get_token = AsyncMock(return_value=MagicMock(token="tok"))
            mock_sync.return_value = True
            r = _make_client(mock_twitch_api=mock_twitch).post(
                "/api/admin/bot-emotes/resync?channel_id=ch-a"
            )

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["channel_id"] == "ch-a"
        assert data[0]["synced"] is True
        # Available names = available channel emotes (aliceFollow) + all globals (Kappa).
        mock_sync.assert_awaited_once()
        _pool, cid, names = mock_sync.await_args.args
        assert cid == "ch-a"
        assert names == ["aliceFollow", "Kappa"]
