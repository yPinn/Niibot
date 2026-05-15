"""Tests for api.routers.stats_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool
from routers.stats_router import router as _stats_router

CHANNEL_ID = "ch-123"


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
    app.include_router(_stats_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    return TestClient(app, raise_server_exceptions=False)


_DEFAULT_CHATTERS = [{"username": "alice", "display_name": "Alice", "message_count": 100}]
_DEFAULT_COMMANDS = [{"command_name": "!hi", "usage_count": 50}]


def _mock_repo(
    chatters=None,
    commands=None,
    total_messages=100,
    total_commands=50,
) -> MagicMock:
    repo = MagicMock()
    repo.list_top_chatters = AsyncMock(
        return_value=_DEFAULT_CHATTERS if chatters is None else chatters
    )
    repo.list_top_commands_from_config = AsyncMock(
        return_value=_DEFAULT_COMMANDS if commands is None else commands
    )
    repo.get_total_messages = AsyncMock(return_value=total_messages)
    repo.get_total_commands_from_config = AsyncMock(return_value=total_commands)
    return repo


# ── GET /api/stats/channel ────────────────────────────────────────────────────


class TestGetChannelStats:
    def test_happy_path_returns_stats(self):
        repo = _mock_repo()
        with patch("routers.stats_router.AnalyticsRepository", return_value=repo):
            r = _make_client().get("/api/stats/channel")
        assert r.status_code == 200
        data = r.json()
        assert data["total_messages"] == 100
        assert data["total_commands"] == 50
        assert data["top_chatters"][0]["username"] == "alice"
        assert data["top_commands"][0]["name"] == "!hi"
        assert data["top_commands"][0]["count"] == 50

    def test_empty_results_returns_zeroes(self):
        repo = _mock_repo(chatters=[], commands=[], total_messages=0, total_commands=0)
        with patch("routers.stats_router.AnalyticsRepository", return_value=repo):
            r = _make_client().get("/api/stats/channel")
        assert r.status_code == 200
        data = r.json()
        assert data["top_chatters"] == []
        assert data["top_commands"] == []
        assert data["total_messages"] == 0

    def test_cache_control_header_set(self):
        repo = _mock_repo(chatters=[], commands=[], total_messages=0, total_commands=0)
        with patch("routers.stats_router.AnalyticsRepository", return_value=repo):
            r = _make_client().get("/api/stats/channel")
        assert "max-age=300" in r.headers.get("cache-control", "")

    def test_days_param_forwarded_to_repo(self):
        repo = _mock_repo(chatters=[], commands=[], total_messages=0, total_commands=0)
        with patch("routers.stats_router.AnalyticsRepository", return_value=repo):
            _make_client().get("/api/stats/channel?days=7")
        repo.get_total_messages.assert_awaited_once_with(CHANNEL_ID, days=7)
        repo.list_top_chatters.assert_awaited_once_with(CHANNEL_ID, days=7, limit=10)

    def test_chatter_display_name_optional(self):
        repo = _mock_repo(chatters=[{"username": "bob", "display_name": None, "message_count": 5}])
        with patch("routers.stats_router.AnalyticsRepository", return_value=repo):
            r = _make_client().get("/api/stats/channel")
        assert r.status_code == 200
        assert r.json()["top_chatters"][0]["display_name"] is None

    def test_db_error_returns_500(self):
        repo = _mock_repo()
        repo.list_top_chatters = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("routers.stats_router.AnalyticsRepository", return_value=repo):
            r = _make_client().get("/api/stats/channel")
        assert r.status_code == 500
        assert "statistics" in r.json()["detail"].lower()
