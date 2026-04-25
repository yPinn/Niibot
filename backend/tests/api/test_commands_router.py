"""Tests for api.routers.commands_router."""

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
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from routers.commands_router import router as _commands_router

CHANNEL_ID = "ch-123"

_CMD_CONFIG = {
    "id": 1,
    "channel_id": CHANNEL_ID,
    "command_name": "shoutout",
    "command_type": "custom",
    "enabled": True,
    "custom_response": "Check them out!",
    "cooldown": 30,
    "min_role": "everyone",
    "aliases": None,
    "usage_count": 0,
    "description": "",
    "created_at": None,
    "updated_at": None,
}

_PUBLIC_CMD = {
    "name": "!help",
    "description": "Shows help",
    "min_role": "everyone",
    "command_type": "builtin",
}

_USER_INFO = {
    "id": "ch-456",
    "display_name": "StreamerXYZ",
    "avatar": "https://img/avatar.png",
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(mock_twitch_api: MagicMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_commands_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    if mock_twitch_api is not None:
        app.dependency_overrides[get_twitch_api] = lambda: mock_twitch_api
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/commands/configs ──


class TestGetCommandConfigs:
    def test_returns_configs_list(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "list_commands", AsyncMock(return_value=[_CMD_CONFIG])
        ):
            r = _make_client().get("/api/commands/configs")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["command_name"] == "shoutout"

    def test_empty_list_returns_200(self):
        import services.command_config_service as m

        with patch.object(m.CommandConfigService, "list_commands", AsyncMock(return_value=[])):
            r = _make_client().get("/api/commands/configs")
        assert r.status_code == 200
        assert r.json() == []

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "list_commands", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().get("/api/commands/configs")
        assert r.status_code == 500


# ── POST /api/commands/configs ──


class TestCreateCustomCommand:
    def test_creates_command_returns_201(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService,
            "create_custom_command",
            AsyncMock(return_value=_CMD_CONFIG),
        ):
            r = _make_client().post(
                "/api/commands/configs",
                json={"command_name": "shoutout", "custom_response": "Check them out!"},
            )
        assert r.status_code == 201
        assert r.json()["command_name"] == "shoutout"

    def test_invalid_min_role_returns_400(self):
        r = _make_client().post(
            "/api/commands/configs",
            json={"command_name": "test", "custom_response": "hi", "min_role": "admin"},
        )
        assert r.status_code == 400
        assert "min_role" in r.json()["detail"]

    def test_missing_custom_response_returns_400(self):
        r = _make_client().post(
            "/api/commands/configs",
            json={"command_name": "test"},
        )
        assert r.status_code == 400

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "create_custom_command", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().post(
                "/api/commands/configs",
                json={"command_name": "fail", "custom_response": "hello"},
            )
        assert r.status_code == 500


# ── PUT /api/commands/configs/{name} ──


class TestUpdateCommandConfig:
    def test_updates_command(self):
        import services.command_config_service as m

        updated = {**_CMD_CONFIG, "enabled": False}
        with patch.object(
            m.CommandConfigService, "update_command", AsyncMock(return_value=updated)
        ):
            r = _make_client().put("/api/commands/configs/shoutout", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_invalid_min_role_returns_400(self):
        r = _make_client().put(
            "/api/commands/configs/shoutout",
            json={"min_role": "admin"},
        )
        assert r.status_code == 400
        assert "min_role" in r.json()["detail"]

    def test_valid_min_role_passes(self):
        import services.command_config_service as m

        updated = {**_CMD_CONFIG, "min_role": "moderator"}
        with patch.object(
            m.CommandConfigService, "update_command", AsyncMock(return_value=updated)
        ):
            r = _make_client().put("/api/commands/configs/shoutout", json={"min_role": "moderator"})
        assert r.status_code == 200

    def test_not_found_returns_404(self):
        import services.command_config_service as m

        with patch.object(m.CommandConfigService, "update_command", AsyncMock(return_value=None)):
            r = _make_client().put("/api/commands/configs/missing", json={"enabled": True})
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "update_command", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().put("/api/commands/configs/shoutout", json={"enabled": True})
        assert r.status_code == 500


# ── PATCH /api/commands/configs/{name}/toggle ──


class TestToggleCommandConfig:
    def test_toggles_command(self):
        import services.command_config_service as m

        toggled = {**_CMD_CONFIG, "enabled": False}
        with patch.object(
            m.CommandConfigService, "toggle_command", AsyncMock(return_value=toggled)
        ):
            r = _make_client().patch(
                "/api/commands/configs/shoutout/toggle", json={"enabled": False}
            )
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_not_found_returns_404(self):
        import services.command_config_service as m

        with patch.object(m.CommandConfigService, "toggle_command", AsyncMock(return_value=None)):
            r = _make_client().patch("/api/commands/configs/missing/toggle", json={"enabled": True})
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "toggle_command", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().patch("/api/commands/configs/fail/toggle", json={"enabled": True})
        assert r.status_code == 500


# ── DELETE /api/commands/configs/{name} ──


class TestDeleteCustomCommand:
    def test_deletes_command_returns_204(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "delete_custom_command", AsyncMock(return_value=True)
        ):
            r = _make_client().delete("/api/commands/configs/shoutout")
        assert r.status_code == 204

    def test_not_found_returns_404(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "delete_custom_command", AsyncMock(return_value=False)
        ):
            r = _make_client().delete("/api/commands/configs/missing")
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService,
            "delete_custom_command",
            AsyncMock(side_effect=RuntimeError),
        ):
            r = _make_client().delete("/api/commands/configs/shoutout")
        assert r.status_code == 500


# ── GET /api/commands/public/{username} ──


class TestGetPublicCommands:
    def test_returns_channel_and_commands(self):
        import services.command_config_service as m

        mock_api = MagicMock()
        mock_api.get_user_by_login = AsyncMock(return_value=_USER_INFO)

        with patch.object(
            m.CommandConfigService, "list_public_commands", AsyncMock(return_value=[_PUBLIC_CMD])
        ):
            r = _make_client(mock_twitch_api=mock_api).get("/api/commands/public/streamerxyz")
        assert r.status_code == 200
        data = r.json()
        assert data["channel"]["display_name"] == "StreamerXYZ"
        assert len(data["commands"]) == 1
        assert data["commands"][0]["name"] == "!help"

    def test_unknown_username_returns_404(self):
        mock_api = MagicMock()
        mock_api.get_user_by_login = AsyncMock(return_value=None)
        r = _make_client(mock_twitch_api=mock_api).get("/api/commands/public/nobody")
        assert r.status_code == 404

    def test_twitch_api_exception_returns_500(self):
        mock_api = MagicMock()
        mock_api.get_user_by_login = AsyncMock(side_effect=RuntimeError("api down"))
        r = _make_client(mock_twitch_api=mock_api).get("/api/commands/public/streamer")
        assert r.status_code == 500
