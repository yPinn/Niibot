"""Tests for api.routers.game_queue_router."""

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
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    get_current_channel_id,
    get_db_pool,
    get_game_queue_service,
    get_twitch_api,
    require_activated,
)
from routers.game_queue_router import router as _gq_router

CHANNEL_ID = "ch-123"
_NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

_ENTRY = {
    "id": 1,
    "channel_id": CHANNEL_ID,
    "user_id": "u1",
    "user_name": "alice",
    "redeemed_at": _NOW,
    "position": 0,
    "batch": 0,
}

_SETTINGS = {"id": 1, "channel_id": CHANNEL_ID, "group_size": 4, "enabled": True}

_STATE = {
    "current_batch": [_ENTRY],
    "next_batch": [],
    "full_queue": [_ENTRY],
    "group_size": 4,
    "enabled": True,
    "total_active": 1,
}

_CLEAR_STATE = {
    **_STATE,
    "cleared_count": 1,
    "full_queue": [],
    "current_batch": [],
    "next_batch": [],
}

_PUBLIC_STATE = {
    "current_batch": [_ENTRY],
    "next_batch": [],
    "group_size": 4,
    "enabled": True,
    "total_active": 1,
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(
    mock_service: MagicMock | None = None,
    mock_twitch_api: MagicMock | None = None,
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_gq_router)
    app.dependency_overrides[require_activated] = lambda: None
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    if mock_service is not None:
        app.dependency_overrides[get_game_queue_service] = lambda: mock_service
    if mock_twitch_api is not None:
        app.dependency_overrides[get_twitch_api] = lambda: mock_twitch_api
    return TestClient(app, raise_server_exceptions=False)


def _svc(*, state=None, clear_state=None, settings=None, public_state=None):
    svc = MagicMock()
    svc.get_queue_state = AsyncMock(return_value=state or _STATE)
    svc.advance_batch = AsyncMock(return_value=state or _STATE)
    svc.remove_player = AsyncMock(return_value=state or _STATE)
    svc.promote_player = AsyncMock(return_value=state or _STATE)
    svc.clear_queue = AsyncMock(return_value=clear_state or _CLEAR_STATE)
    svc.get_settings = AsyncMock(return_value=settings or _SETTINGS)
    svc.update_settings = AsyncMock(return_value=settings or _SETTINGS)
    svc.get_public_state = AsyncMock(return_value=public_state or _PUBLIC_STATE)
    return svc


# ── GET /api/game-queue/state ────────────────────────────────────────────────


class TestGetQueueState:
    def test_returns_state(self):
        r = _make_client(mock_service=_svc()).get("/api/game-queue/state")
        assert r.status_code == 200
        assert r.json()["total_active"] == 1

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.get_queue_state = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).get("/api/game-queue/state")
        assert r.status_code == 500


# ── POST /api/game-queue/advance ─────────────────────────────────────────────


class TestAdvanceBatch:
    def test_advances_and_returns_state(self):
        r = _make_client(mock_service=_svc()).post("/api/game-queue/advance")
        assert r.status_code == 200
        assert "current_batch" in r.json()

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.advance_batch = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).post("/api/game-queue/advance")
        assert r.status_code == 500


# ── DELETE /api/game-queue/entries/{entry_id} ────────────────────────────────


class TestRemovePlayer:
    def test_removes_and_returns_state(self):
        r = _make_client(mock_service=_svc()).delete("/api/game-queue/entries/1")
        assert r.status_code == 200
        assert "full_queue" in r.json()

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.remove_player = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).delete("/api/game-queue/entries/1")
        assert r.status_code == 500


# ── POST /api/game-queue/entries/{entry_id}/promote ──────────────────────────


class TestPromotePlayer:
    def test_promotes_and_returns_state(self):
        r = _make_client(mock_service=_svc()).post("/api/game-queue/entries/1/promote")
        assert r.status_code == 200

    def test_not_found_returns_404(self):
        svc = _svc()
        svc.promote_player = AsyncMock(return_value=None)
        r = _make_client(mock_service=svc).post("/api/game-queue/entries/99/promote")
        assert r.status_code == 404

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.promote_player = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).post("/api/game-queue/entries/1/promote")
        assert r.status_code == 500


# ── DELETE /api/game-queue/clear ─────────────────────────────────────────────


class TestClearQueue:
    def test_clears_and_returns_cleared_count(self):
        r = _make_client(mock_service=_svc()).delete("/api/game-queue/clear")
        assert r.status_code == 200
        assert r.json()["cleared_count"] == 1

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.clear_queue = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).delete("/api/game-queue/clear")
        assert r.status_code == 500


# ── GET /api/game-queue/settings ─────────────────────────────────────────────


class TestGetSettings:
    def test_returns_settings(self):
        r = _make_client(mock_service=_svc()).get("/api/game-queue/settings")
        assert r.status_code == 200
        assert r.json()["group_size"] == 4

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.get_settings = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).get("/api/game-queue/settings")
        assert r.status_code == 500


# ── PUT /api/game-queue/settings ─────────────────────────────────────────────


class TestUpdateSettings:
    def test_updates_group_size(self):
        r = _make_client(mock_service=_svc()).put(
            "/api/game-queue/settings", json={"group_size": 5}
        )
        assert r.status_code == 200

    def test_updates_enabled(self):
        r = _make_client(mock_service=_svc()).put(
            "/api/game-queue/settings", json={"enabled": False}
        )
        assert r.status_code == 200

    def test_no_fields_returns_400(self):
        r = _make_client(mock_service=_svc()).put("/api/game-queue/settings", json={})
        assert r.status_code == 400

    def test_service_error_returns_500(self):
        svc = _svc()
        svc.update_settings = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=svc).put("/api/game-queue/settings", json={"enabled": True})
        assert r.status_code == 500


# ── GET /api/game-queue/public/{username} ────────────────────────────────────


class TestGetPublicQueueState:
    def test_returns_public_state(self):
        api = MagicMock()
        api.get_user_by_login = AsyncMock(return_value={"id": CHANNEL_ID})
        r = _make_client(mock_service=_svc(), mock_twitch_api=api).get(
            "/api/game-queue/public/streamer"
        )
        assert r.status_code == 200
        assert r.json()["group_size"] == 4

    def test_unknown_user_returns_404(self):
        api = MagicMock()
        api.get_user_by_login = AsyncMock(return_value=None)
        r = _make_client(mock_service=_svc(), mock_twitch_api=api).get(
            "/api/game-queue/public/nobody"
        )
        assert r.status_code == 404

    def test_api_error_returns_500(self):
        api = MagicMock()
        api.get_user_by_login = AsyncMock(side_effect=RuntimeError)
        r = _make_client(mock_service=_svc(), mock_twitch_api=api).get(
            "/api/game-queue/public/streamer"
        )
        assert r.status_code == 500
