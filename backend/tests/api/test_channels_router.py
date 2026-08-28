"""Tests for api.routers.channels_router — mod-status and grant-mod endpoints."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-999")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.channel_service as cs
from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from core.error_handlers import register_exception_handlers
from routers.channels_router import router as _channels_router

CHANNEL_ID = "ch-123"


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(
    *,
    twitch_api: MagicMock | None = None,
) -> TestClient:
    """Build a TestClient with all heavyweight dependencies stubbed out."""
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_channels_router)

    mock_api = twitch_api or MagicMock()
    mock_pool = AsyncMock()

    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_twitch_api] = lambda: mock_api
    app.dependency_overrides[get_db_pool] = lambda: mock_pool

    return TestClient(app, raise_server_exceptions=False)


# ============================================
# GET /api/channels/twitch/mod-status
# ============================================


class TestGetBotModStatus:
    def test_returns_is_moderator_true(self):
        mock_api = MagicMock()
        mock_api.check_bot_is_moderator = AsyncMock(return_value=True)
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.get("/api/channels/twitch/mod-status")

        assert r.status_code == 200
        assert r.json() == {"is_moderator": True}

    def test_returns_is_moderator_false(self):
        mock_api = MagicMock()
        mock_api.check_bot_is_moderator = AsyncMock(return_value=False)
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.get("/api/channels/twitch/mod-status")

        assert r.status_code == 200
        assert r.json() == {"is_moderator": False}

    def test_returns_403_with_reauth_header_when_token_missing(self):
        client = _make_client()

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value=None)
        ):
            r = client.get("/api/channels/twitch/mod-status")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"

    def test_passes_bot_id_from_settings_to_api(self):
        mock_api = MagicMock()
        mock_api.check_bot_is_moderator = AsyncMock(return_value=False)
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            client.get("/api/channels/twitch/mod-status")

        expected_bot_id = get_settings().bot_id
        mock_api.check_bot_is_moderator.assert_awaited_once_with(
            CHANNEL_ID, expected_bot_id, "valid-token"
        )


# ============================================
# POST /api/channels/twitch/grant-mod
# ============================================


class TestGrantBotMod:
    def _helix_response(self, status_code: int, body: str = "") -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = body
        return resp

    def test_204_returns_granted_true(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(204))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 200
        assert r.json() == {"granted": True, "already_mod": False}

    def test_422_returns_already_mod(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(422))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 200
        assert r.json() == {"granted": False, "already_mod": True}

    def test_401_from_helix_returns_403_with_reauth_header(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(401))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"

    def test_403_from_helix_returns_403_with_reauth_header(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(403))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"

    def test_missing_token_returns_403_with_reauth_header(self):
        client = _make_client()

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value=None)
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"

    def test_add_moderator_exception_returns_500(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(side_effect=Exception("network failure"))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 500

    def test_unexpected_helix_status_returns_502(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(500, "server error"))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 502

    def test_passes_bot_id_and_channel_id_to_api(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(204))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            client.post("/api/channels/twitch/grant-mod")

        expected_bot_id = get_settings().bot_id
        mock_api.add_moderator.assert_awaited_once_with(CHANNEL_ID, expected_bot_id, "valid-token")
