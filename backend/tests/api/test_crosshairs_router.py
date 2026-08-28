"""Tests for api.routers.crosshairs_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api, require_activated
from core.error_handlers import register_exception_handlers
from routers.crosshairs_router import _user_lookup_cache
from routers.crosshairs_router import router as _xh_router

CHANNEL_ID = "ch-123"
_NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
_XH_ID = str(uuid4())

_XH_ROW = {
    "id": _XH_ID,
    "channel_id": CHANNEL_ID,
    "game": "valorant",
    "name": "Default",
    "code": "0;P;c;1;h;0;0l;4;0o;0;0a;0;0f;0;0m;0;0e;1;1b;0",
    "description": None,
    "display_order": 0,
    "copy_count": 3,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_XH_PUBLIC_ROW = {**_XH_ROW, "channel_name": "streamer"}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    _user_lookup_cache.clear()
    yield
    get_settings.cache_clear()
    _user_lookup_cache.clear()


def _make_client(
    mock_twitch_api: MagicMock | None = None,
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_xh_router)
    app.dependency_overrides[require_activated] = lambda: None
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    if mock_twitch_api is not None:
        app.dependency_overrides[get_twitch_api] = lambda: mock_twitch_api
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/crosshairs/public ───────────────────────────────────────────────


class TestListAllPublicCrosshairs:
    def test_returns_list(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_all_public = AsyncMock(return_value=[_XH_PUBLIC_ROW])
            r = _make_client().get("/api/crosshairs/public")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Default"

    def test_filters_by_game(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_all_public = AsyncMock(return_value=[_XH_PUBLIC_ROW])
            r = _make_client().get("/api/crosshairs/public?game=valorant")
        assert r.status_code == 200

    def test_empty_returns_200(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_all_public = AsyncMock(return_value=[])
            r = _make_client().get("/api/crosshairs/public")
        assert r.status_code == 200
        assert r.json() == []

    def test_repo_error_returns_500(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_all_public = AsyncMock(side_effect=RuntimeError)
            r = _make_client().get("/api/crosshairs/public")
        assert r.status_code == 500


# ── GET /api/crosshairs/public/{username} ────────────────────────────────────


class TestGetPublicCrosshairs:
    def test_returns_channel_and_crosshairs(self):
        api = MagicMock()
        api.get_user_by_login = AsyncMock(
            return_value={"id": CHANNEL_ID, "display_name": "Streamer", "avatar": None}
        )
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_by_channel = AsyncMock(return_value=[_XH_ROW])
            r = _make_client(mock_twitch_api=api).get("/api/crosshairs/public/streamer")
        assert r.status_code == 200
        data = r.json()
        assert data["channel"]["display_name"] == "Streamer"
        assert len(data["crosshairs"]) == 1

    def test_unknown_user_returns_404(self):
        api = MagicMock()
        api.get_user_by_login = AsyncMock(return_value=None)
        r = _make_client(mock_twitch_api=api).get("/api/crosshairs/public/nobody")
        assert r.status_code == 404

    def test_uses_cache_on_second_call(self):
        api = MagicMock()
        api.get_user_by_login = AsyncMock(
            return_value={"id": CHANNEL_ID, "display_name": "Streamer", "avatar": None}
        )
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_by_channel = AsyncMock(return_value=[])
            client = _make_client(mock_twitch_api=api)
            client.get("/api/crosshairs/public/streamer")
            client.get("/api/crosshairs/public/streamer")
        # Second call should use cache — Twitch API called once
        api.get_user_by_login.assert_awaited_once()


# ── POST /api/crosshairs/public/{crosshair_id}/copy ──────────────────────────


class TestRecordCrosshairCopy:
    def test_returns_204(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.increment_copy = AsyncMock(return_value=None)
            r = _make_client().post(f"/api/crosshairs/public/{_XH_ID}/copy")
        assert r.status_code == 204

    def test_repo_error_is_swallowed(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.increment_copy = AsyncMock(side_effect=RuntimeError)
            r = _make_client().post(f"/api/crosshairs/public/{_XH_ID}/copy")
        assert r.status_code == 204


# ── GET /api/crosshairs ───────────────────────────────────────────────────────


class TestListCrosshairs:
    def test_returns_channel_crosshairs(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_by_channel = AsyncMock(return_value=[_XH_ROW])
            r = _make_client().get("/api/crosshairs")
        assert r.status_code == 200
        assert r.json()[0]["game"] == "valorant"

    def test_repo_error_returns_500(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.list_by_channel = AsyncMock(side_effect=RuntimeError)
            r = _make_client().get("/api/crosshairs")
        assert r.status_code == 500


# ── POST /api/crosshairs ──────────────────────────────────────────────────────


class TestCreateCrosshair:
    def test_creates_and_returns_201(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.create = AsyncMock(return_value=_XH_ROW)
            r = _make_client().post(
                "/api/crosshairs",
                json={"game": "valorant", "name": "Default", "code": "0;P;c;1"},
            )
        assert r.status_code == 201
        assert r.json()["name"] == "Default"

    def test_invalid_game_returns_400(self):
        r = _make_client().post(
            "/api/crosshairs",
            json={"game": "cs2", "name": "Test", "code": "abc"},
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "CROSSHAIR.INVALID"
        assert "cs2" not in r.text

    def test_repo_error_returns_500(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.create = AsyncMock(side_effect=RuntimeError)
            r = _make_client().post(
                "/api/crosshairs",
                json={"game": "valorant", "name": "x", "code": "y"},
            )
        assert r.status_code == 500


# ── PATCH /api/crosshairs/{crosshair_id} ─────────────────────────────────────


class TestUpdateCrosshair:
    def test_updates_and_returns_200(self):
        updated = {**_XH_ROW, "name": "Updated"}
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.update = AsyncMock(return_value=updated)
            r = _make_client().patch(f"/api/crosshairs/{_XH_ID}", json={"name": "Updated"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated"

    def test_not_found_returns_404(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.update = AsyncMock(return_value=None)
            r = _make_client().patch(f"/api/crosshairs/{_XH_ID}", json={"name": "X"})
        assert r.status_code == 404

    def test_invalid_game_returns_400(self):
        r = _make_client().patch(f"/api/crosshairs/{_XH_ID}", json={"game": "cs2"})
        assert r.status_code == 400

    def test_repo_error_returns_500(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.update = AsyncMock(side_effect=RuntimeError)
            r = _make_client().patch(f"/api/crosshairs/{_XH_ID}", json={"name": "X"})
        assert r.status_code == 500


# ── DELETE /api/crosshairs/{crosshair_id} ────────────────────────────────────


class TestDeleteCrosshair:
    def test_deletes_returns_204(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.delete = AsyncMock(return_value=True)
            r = _make_client().delete(f"/api/crosshairs/{_XH_ID}")
        assert r.status_code == 204

    def test_not_found_returns_404(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.delete = AsyncMock(return_value=False)
            r = _make_client().delete(f"/api/crosshairs/{_XH_ID}")
        assert r.status_code == 404

    def test_repo_error_returns_500(self):
        with patch("routers.crosshairs_router.CrosshairRepository") as mock_repo:
            mock_repo.return_value.delete = AsyncMock(side_effect=RuntimeError)
            r = _make_client().delete(f"/api/crosshairs/{_XH_ID}")
        assert r.status_code == 500
