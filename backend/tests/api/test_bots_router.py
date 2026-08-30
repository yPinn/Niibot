"""Tests for api.routers.bots_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")
os.environ.setdefault("TWITCH_BOT_URL", "http://twitch-bot:8080")
os.environ.setdefault("DISCORD_BOT_URL", "http://discord-bot:8081")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_user_id, require_activated
from routers.bots_router import router as _bots_router


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client() -> TestClient:
    mock_settings = MagicMock()
    mock_settings.twitch_bot_url = "http://twitch-bot:8080"
    mock_settings.discord_bot_url = "http://discord-bot:8081"

    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_bots_router)
    app.dependency_overrides[get_current_user_id] = lambda: "user-123"
    app.dependency_overrides[require_activated] = lambda: None
    app.dependency_overrides[get_settings] = lambda: mock_settings
    return TestClient(app, raise_server_exceptions=False)


def _http_response(status_code: int = 200, data: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = data or {}
    return r


# ── GET /api/bots/twitch/status ───────────────────────────────────────────────


class TestTwitchBotStatus:
    def test_online_200_maps_all_fields(self):
        payload = {
            "service": "twitch-bot",
            "version": "1.2.3",
            "git_commit": "abc",
            "started_at": "2024-01-01T00:00:00Z",
            "bot_id": "bot-1",
            "uptime_seconds": 3600,
            "ready": True,
            "connected_channels": 5,
            "components": 3,
            "ai_model": "gpt-4",
        }
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(return_value=_http_response(200, payload))
            r = _make_client().get("/api/bots/twitch/status")
        assert r.status_code == 200
        body = r.json()
        assert body["online"] is True
        assert body["service"] == "twitch-bot"
        assert body["uptime_seconds"] == 3600
        assert body["connected_channels"] == 5
        assert body["ai_model"] == "gpt-4"

    def test_non_200_returns_offline(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(return_value=_http_response(503))
            r = _make_client().get("/api/bots/twitch/status")
        assert r.status_code == 200
        assert r.json()["online"] is False

    def test_timeout_returns_offline(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            r = _make_client().get("/api/bots/twitch/status")
        assert r.status_code == 200
        assert r.json()["online"] is False

    def test_connect_error_returns_offline(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            r = _make_client().get("/api/bots/twitch/status")
        assert r.status_code == 200
        assert r.json()["online"] is False

    def test_generic_exception_returns_offline(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(side_effect=RuntimeError("unexpected"))
            r = _make_client().get("/api/bots/twitch/status")
        assert r.status_code == 200
        assert r.json()["online"] is False


# ── GET /api/bots/discord/status ─────────────────────────────────────────────


class TestDiscordBotStatus:
    def test_online_maps_discord_fields(self):
        payload = {"guilds": 3, "cogs": 8, "ws_latency_ms": 42}
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(return_value=_http_response(200, payload))
            r = _make_client().get("/api/bots/discord/status")
        assert r.status_code == 200
        body = r.json()
        assert body["online"] is True
        assert body["guilds"] == 3
        assert body["ws_latency_ms"] == 42

    def test_offline_when_unreachable(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(side_effect=httpx.ConnectError("down"))
            r = _make_client().get("/api/bots/discord/status")
        assert r.json()["online"] is False


# ── GET /api/bots/twitch/health ───────────────────────────────────────────────


class TestTwitchBotHealth:
    def test_healthy_200_proxies_json(self):
        payload = {"status": "ok", "uptime": 1000}
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(return_value=_http_response(200, payload))
            r = _make_client().get("/api/bots/twitch/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_non_200_returns_unhealthy(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(return_value=_http_response(503))
            r = _make_client().get("/api/bots/twitch/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "unhealthy"
        assert body["bot_offline"] is True

    def test_exception_returns_unhealthy(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(side_effect=httpx.ConnectError("down"))
            r = _make_client().get("/api/bots/twitch/health")
        assert r.status_code == 200
        assert r.json()["bot_offline"] is True


# ── GET /api/bots/discord/health ─────────────────────────────────────────────


class TestDiscordBotHealth:
    def test_healthy_200_proxies_json(self):
        payload = {"status": "ok", "latency_ms": 50}
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(return_value=_http_response(200, payload))
            r = _make_client().get("/api/bots/discord/health")
        assert r.status_code == 200
        assert r.json()["latency_ms"] == 50

    def test_exception_returns_unhealthy(self):
        with patch("routers.bots_router._http_client") as mock_http:
            mock_http.get = AsyncMock(side_effect=RuntimeError("crash"))
            r = _make_client().get("/api/bots/discord/health")
        assert r.json()["bot_offline"] is True
