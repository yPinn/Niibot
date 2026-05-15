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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    get_channel_service,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
)
from routers.admin_router import router as _admin_router

OWNER_ID = "owner-123"
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
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_admin_router)
    app.dependency_overrides[get_current_channel_id] = lambda: channel_id
    app.dependency_overrides[get_db_pool] = lambda: mock_pool or AsyncMock()
    if mock_twitch_api is not None:
        app.dependency_overrides[get_twitch_api] = lambda: mock_twitch_api
    if mock_channel_service is not None:
        app.dependency_overrides[get_channel_service] = lambda: mock_channel_service
    return TestClient(app, raise_server_exceptions=False)


def _make_pool(*, fetchrow=None, fetch=None, execute=None) -> MagicMock:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    conn.fetch.return_value = fetch or []
    conn.execute.return_value = execute or "DELETE 0"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    # activation-codes endpoint calls pool.fetch() directly (not via acquire)
    pool.fetch = AsyncMock(return_value=fetch or [])
    return pool


# ── require_owner guard ──────────────────────────────────────────────────────


class TestRequireOwner:
    def test_non_owner_gets_403(self):
        r = _make_client(channel_id="not-the-owner").get("/api/admin/activation-codes")
        assert r.status_code == 403

    def test_owner_passes_guard(self):
        r = _make_client(mock_pool=_make_pool(fetch=[])).get("/api/admin/activation-codes")
        assert r.status_code == 200


# ── GET /api/admin/activation-codes ─────────────────────────────────────────


class TestGetPendingActivationCodes:
    def test_returns_empty_list(self):
        pool = _make_pool(fetch=[])
        r = _make_client(mock_pool=pool).get("/api/admin/activation-codes")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_pending_codes(self):
        dict_row = {
            "platform_user_id": "u1",
            "expires_at": _NOW,
            "code_plain": "123456",
            "display_name": "Alice",
            "avatar": None,
            "username": "alice",
        }
        pool = _make_pool(fetch=[dict_row])
        r = _make_client(mock_pool=pool).get("/api/admin/activation-codes")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["platform_user_id"] == "u1"


# ── DELETE /api/admin/activation-codes/{platform_user_id} ───────────────────


class TestRevokeActivationCode:
    def test_revoke_existing_code(self):
        with patch("routers.admin_router.ActivationCodeRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.invalidate = AsyncMock(return_value=True)
            r = _make_client().delete("/api/admin/activation-codes/user1")
        assert r.status_code == 200
        assert r.json()["revoked"] is True

    def test_revoke_missing_code_returns_404(self):
        with patch("routers.admin_router.ActivationCodeRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.invalidate = AsyncMock(return_value=False)
            r = _make_client().delete("/api/admin/activation-codes/unknown")
        assert r.status_code == 404


# ── GET /api/admin/activation-requests ──────────────────────────────────────


class TestGetActivationRequests:
    def test_returns_empty_list(self):
        with patch("routers.admin_router.ActivationRequestRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.list_pending = AsyncMock(return_value=[])
            r = _make_client().get("/api/admin/activation-requests")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_pending_requests(self):
        pending = [
            {
                "id": 1,
                "platform_user_id": "u1",
                "display_name": "Alice",
                "username": "alice",
                "avatar": None,
                "note": "please",
                "created_at": _NOW,
            }
        ]
        with patch("routers.admin_router.ActivationRequestRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.list_pending = AsyncMock(return_value=pending)
            r = _make_client().get("/api/admin/activation-requests")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["platform_user_id"] == "u1"


# ── POST /api/admin/activation-requests/{id}/approve ────────────────────────


class TestApproveActivationRequest:
    def test_approve_returns_approved_true(self):
        with patch("routers.admin_router.ActivationRequestRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.approve = AsyncMock(return_value=True)
            r = _make_client().post("/api/admin/activation-requests/1/approve")
        assert r.status_code == 200
        assert r.json()["approved"] is True

    def test_approve_missing_request_returns_404(self):
        with patch("routers.admin_router.ActivationRequestRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.approve = AsyncMock(return_value=False)
            r = _make_client().post("/api/admin/activation-requests/99/approve")
        assert r.status_code == 404


# ── POST /api/admin/activation-requests/{id}/reject ─────────────────────────


class TestRejectActivationRequest:
    def test_reject_returns_rejected_true(self):
        with patch("routers.admin_router.ActivationRequestRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.reject = AsyncMock(return_value=True)
            r = _make_client().post("/api/admin/activation-requests/1/reject")
        assert r.status_code == 200
        assert r.json()["rejected"] is True

    def test_reject_missing_request_returns_404(self):
        with patch("routers.admin_router.ActivationRequestRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.reject = AsyncMock(return_value=False)
            r = _make_client().post("/api/admin/activation-requests/99/reject")
        assert r.status_code == 404


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
