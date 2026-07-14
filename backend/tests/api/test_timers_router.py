"""Tests for api.routers.timers_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool, require_activated
from routers.timers_router import router as _timers_router

CHANNEL_ID = "ch-timers"

_TIMER = {
    "id": 1,
    "channel_id": CHANNEL_ID,
    "timer_name": "social",
    "interval_seconds": 300,
    "min_lines": 5,
    "message_template": "Follow on Twitter!",
    "enabled": True,
    "announce": False,
    "command_alias": None,
    "created_at": None,
    "updated_at": None,
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client() -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_timers_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[require_activated] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _make_client_not_activated() -> TestClient:
    """Client where require_activated rejects the caller, for gate tests."""
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_timers_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()

    def _reject() -> None:
        raise HTTPException(status_code=403, detail="Account not activated")

    app.dependency_overrides[require_activated] = _reject
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/timers/configs ──


class TestGetTimerConfigs:
    def test_returns_timers_list(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "list_timers", AsyncMock(return_value=[_TIMER])):
            r = _make_client().get("/api/timers/configs")
        assert r.status_code == 200
        assert r.json()[0]["timer_name"] == "social"

    def test_empty_list_returns_200(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "list_timers", AsyncMock(return_value=[])):
            r = _make_client().get("/api/timers/configs")
        assert r.status_code == 200
        assert r.json() == []

    def test_service_exception_returns_500(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "list_timers", AsyncMock(side_effect=RuntimeError)):
            r = _make_client().get("/api/timers/configs")
        assert r.status_code == 500


# ── POST /api/timers/configs ──


class TestCreateTimer:
    def test_creates_timer_returns_201(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "create_timer", AsyncMock(return_value=_TIMER)):
            r = _make_client().post(
                "/api/timers/configs",
                json={
                    "timer_name": "social",
                    "interval_seconds": 300,
                    "message_template": "Follow on Twitter!",
                },
            )
        assert r.status_code == 201
        assert r.json()["timer_name"] == "social"

    def test_value_error_returns_400(self):
        import services.timer_service as m

        with patch.object(
            m.TimerService,
            "create_timer",
            AsyncMock(side_effect=ValueError("interval too short")),
        ):
            r = _make_client().post(
                "/api/timers/configs",
                json={
                    "timer_name": "bad",
                    "interval_seconds": 300,
                    "message_template": "test",
                },
            )
        assert r.status_code == 400
        assert "interval too short" in r.json()["detail"]

    def test_interval_below_minimum_returns_422(self):
        r = _make_client().post(
            "/api/timers/configs",
            json={
                "timer_name": "toosoon",
                "interval_seconds": 59,
                "message_template": "test",
            },
        )
        assert r.status_code == 422

    def test_service_exception_returns_500(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "create_timer", AsyncMock(side_effect=RuntimeError)):
            r = _make_client().post(
                "/api/timers/configs",
                json={
                    "timer_name": "fail",
                    "interval_seconds": 300,
                    "message_template": "test",
                },
            )
        assert r.status_code == 500


# ── PUT /api/timers/configs/{name} ──


class TestUpdateTimer:
    def test_updates_timer(self):
        import services.timer_service as m

        updated = {**_TIMER, "interval_seconds": 600}
        with patch.object(m.TimerService, "update_timer", AsyncMock(return_value=updated)):
            r = _make_client().put("/api/timers/configs/social", json={"interval_seconds": 600})
        assert r.status_code == 200
        assert r.json()["interval_seconds"] == 600

    def test_value_error_returns_400(self):
        import services.timer_service as m

        with patch.object(
            m.TimerService,
            "update_timer",
            AsyncMock(side_effect=ValueError("min_lines negative")),
        ):
            r = _make_client().put("/api/timers/configs/social", json={"min_lines": -1})
        assert r.status_code == 400
        assert "min_lines negative" in r.json()["detail"]

    def test_not_found_returns_404(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "update_timer", AsyncMock(return_value=None)):
            r = _make_client().put("/api/timers/configs/missing", json={"enabled": True})
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "update_timer", AsyncMock(side_effect=RuntimeError)):
            r = _make_client().put("/api/timers/configs/social", json={"enabled": True})
        assert r.status_code == 500


# ── PATCH /api/timers/configs/{name}/toggle ──


class TestToggleTimer:
    def test_toggles_timer(self):
        import services.timer_service as m

        toggled = {**_TIMER, "enabled": False}
        with patch.object(m.TimerService, "toggle_timer", AsyncMock(return_value=toggled)):
            r = _make_client().patch("/api/timers/configs/social/toggle", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_not_found_returns_404(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "toggle_timer", AsyncMock(return_value=None)):
            r = _make_client().patch("/api/timers/configs/missing/toggle", json={"enabled": True})
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "toggle_timer", AsyncMock(side_effect=RuntimeError)):
            r = _make_client().patch("/api/timers/configs/social/toggle", json={"enabled": True})
        assert r.status_code == 500


# ── DELETE /api/timers/configs/{name} ──


class TestDeleteTimer:
    def test_deletes_timer_returns_204(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "delete_timer", AsyncMock(return_value=True)):
            r = _make_client().delete("/api/timers/configs/social")
        assert r.status_code == 204

    def test_not_found_returns_404(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "delete_timer", AsyncMock(return_value=False)):
            r = _make_client().delete("/api/timers/configs/missing")
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.timer_service as m

        with patch.object(m.TimerService, "delete_timer", AsyncMock(side_effect=RuntimeError)):
            r = _make_client().delete("/api/timers/configs/social")
        assert r.status_code == 500


# ── require_activated gate ──


class TestActivationGate:
    def test_list_rejected_when_not_activated(self):
        r = _make_client_not_activated().get("/api/timers/configs")
        assert r.status_code == 403

    def test_create_rejected_when_not_activated(self):
        r = _make_client_not_activated().post(
            "/api/timers/configs",
            json={
                "timer_name": "social",
                "interval_seconds": 300,
                "message_template": "hi",
            },
        )
        assert r.status_code == 403
