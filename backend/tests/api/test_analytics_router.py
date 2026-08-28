"""Tests for api.routers.analytics_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool
from core.error_handlers import register_exception_handlers
from routers.analytics_router import router as _analytics_router

CHANNEL_ID = "ch-analytics"
_DT = datetime(2024, 1, 1, 12, 0, 0)

_SUMMARY = {
    "total_sessions": 5,
    "total_stream_hours": 12.5,
    "total_commands": 100,
    "total_follows": 20,
    "total_subs": 5,
    "avg_session_duration": 2.5,
    "recent_sessions": [],
}

_CMD_STAT = {
    "command_name": "!help",
    "usage_count": 10,
    "last_used_at": _DT,
}

_STREAM_EVENT = {
    "event_type": "follow",
    "user_id": "u-1",
    "username": "viewer1",
    "display_name": "Viewer1",
    "metadata": None,
    "occurred_at": _DT,
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
    register_exception_handlers(app)
    app.include_router(_analytics_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/analytics/summary ──


class TestGetAnalyticsSummary:
    def test_returns_200_with_summary_data(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_summary", AsyncMock(return_value=_SUMMARY)):
            r = _make_client().get("/api/analytics/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["total_sessions"] == 5
        assert d["total_stream_hours"] == 12.5
        assert d["recent_sessions"] == []

    def test_days_query_param_accepted(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_summary", AsyncMock(return_value=_SUMMARY)):
            r = _make_client().get("/api/analytics/summary?days=7")
        assert r.status_code == 200

    def test_days_zero_returns_422(self):
        r = _make_client().get("/api/analytics/summary?days=0")
        assert r.status_code == 422

    def test_days_over_365_returns_422(self):
        r = _make_client().get("/api/analytics/summary?days=366")
        assert r.status_code == 422

    def test_service_exception_returns_500(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_summary", AsyncMock(side_effect=RuntimeError("db"))
        ):
            r = _make_client().get("/api/analytics/summary")
        assert r.status_code == 500

    def test_cache_control_header_is_set(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_summary", AsyncMock(return_value=_SUMMARY)):
            r = _make_client().get("/api/analytics/summary")
        assert "private" in r.headers.get("cache-control", "")


# ── GET /api/analytics/sessions/{id}/commands ──


class TestGetSessionCommands:
    def test_returns_commands_list(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_session_commands", AsyncMock(return_value=[_CMD_STAT])
        ):
            r = _make_client().get("/api/analytics/sessions/1/commands")
        assert r.status_code == 200
        assert r.json()[0]["command_name"] == "!help"

    def test_empty_list_returns_200(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_session_commands", AsyncMock(return_value=[])):
            r = _make_client().get("/api/analytics/sessions/1/commands")
        assert r.status_code == 200
        assert r.json() == []

    def test_none_returns_404(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_session_commands", AsyncMock(return_value=None)):
            r = _make_client().get("/api/analytics/sessions/999/commands")
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_session_commands", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().get("/api/analytics/sessions/1/commands")
        assert r.status_code == 500

    def test_cache_control_header_is_set(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_session_commands", AsyncMock(return_value=[])):
            r = _make_client().get("/api/analytics/sessions/1/commands")
        assert "private" in r.headers.get("cache-control", "")


# ── GET /api/analytics/sessions/{id}/events ──


class TestGetSessionEvents:
    def test_returns_events_list(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_session_events", AsyncMock(return_value=[_STREAM_EVENT])
        ):
            r = _make_client().get("/api/analytics/sessions/1/events")
        assert r.status_code == 200
        assert r.json()[0]["event_type"] == "follow"

    def test_none_returns_404(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_session_events", AsyncMock(return_value=None)):
            r = _make_client().get("/api/analytics/sessions/42/events")
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_session_events", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().get("/api/analytics/sessions/1/events")
        assert r.status_code == 500

    def test_cache_control_header_is_set(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_session_events", AsyncMock(return_value=[])):
            r = _make_client().get("/api/analytics/sessions/1/events")
        assert "private" in r.headers.get("cache-control", "")


# ── GET /api/analytics/top-commands ──


class TestGetTopCommands:
    def test_returns_top_commands(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_top_commands", AsyncMock(return_value=[_CMD_STAT])
        ):
            r = _make_client().get("/api/analytics/top-commands")
        assert r.status_code == 200
        assert r.json()[0]["command_name"] == "!help"

    def test_days_and_limit_params_accepted(self):
        import services.analytics_service as m

        with patch.object(m.AnalyticsService, "get_top_commands", AsyncMock(return_value=[])):
            r = _make_client().get("/api/analytics/top-commands?days=7&limit=5")
        assert r.status_code == 200

    def test_limit_zero_returns_422(self):
        r = _make_client().get("/api/analytics/top-commands?limit=0")
        assert r.status_code == 422

    def test_limit_over_100_returns_422(self):
        r = _make_client().get("/api/analytics/top-commands?limit=101")
        assert r.status_code == 422

    def test_service_exception_returns_500(self):
        import services.analytics_service as m

        with patch.object(
            m.AnalyticsService, "get_top_commands", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().get("/api/analytics/top-commands")
        assert r.status_code == 500


# ── POST /api/analytics/sync-roles — rate limit ──


class TestSyncRolesRateLimit:
    def test_rate_limit_exceeded_returns_429(self):
        """_sync_roles_limiter.require() raising 429 must propagate from the endpoint."""
        from routers.analytics_router import _sync_roles_limiter

        with patch.object(_sync_roles_limiter, "allow", return_value=False):
            r = _make_client().post("/api/analytics/sync-roles")

        assert r.status_code == 429
