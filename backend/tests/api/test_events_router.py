"""Tests for api.routers.events_router."""

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
from routers.events_router import router as _events_router

CHANNEL_ID = "ch-events"

_EVENT_CONFIG = {
    "id": 1,
    "channel_id": CHANNEL_ID,
    "event_type": "follow",
    "message_template": "Thanks {user}!",
    "enabled": True,
    "options": {},
    "trigger_count": 0,
    "created_at": None,
    "updated_at": None,
}

_REDEMPTION = {
    "id": 1,
    "channel_id": CHANNEL_ID,
    "action_type": "vip",
    "reward_name": "VIP for a day",
    "enabled": True,
    "created_at": None,
    "updated_at": None,
}

_REWARD = {"id": "r-1", "title": "VIP", "cost": 1000}


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
    app.include_router(_events_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    mock_api = mock_twitch_api or MagicMock()
    app.dependency_overrides[get_twitch_api] = lambda: mock_api
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/events/configs ──


class TestGetEventConfigs:
    def test_returns_configs_list(self):
        import services.event_config_service as m

        with patch.object(
            m.EventConfigService,
            "list_configs_with_counts",
            AsyncMock(return_value=[_EVENT_CONFIG]),
        ):
            r = _make_client().get("/api/events/configs")
        assert r.status_code == 200
        assert r.json()[0]["event_type"] == "follow"

    def test_service_exception_returns_500(self):
        import services.event_config_service as m

        with patch.object(
            m.EventConfigService,
            "list_configs_with_counts",
            AsyncMock(side_effect=RuntimeError),
        ):
            r = _make_client().get("/api/events/configs")
        assert r.status_code == 500


# ── PUT /api/events/configs/{event_type} ──


class TestUpdateEventConfig:
    def test_updates_config(self):
        import services.event_config_service as m

        updated = {**_EVENT_CONFIG, "message_template": "New msg!"}
        with patch.object(m.EventConfigService, "update_config", AsyncMock(return_value=updated)):
            r = _make_client().put(
                "/api/events/configs/follow",
                json={"message_template": "New msg!", "enabled": True},
            )
        assert r.status_code == 200
        assert r.json()["message_template"] == "New msg!"

    def test_invalid_event_type_returns_400(self):
        r = _make_client().put(
            "/api/events/configs/invalid_type",
            json={"message_template": "test", "enabled": True},
        )
        assert r.status_code == 400
        assert "invalid_type" in r.json()["detail"]

    def test_all_valid_event_types_accepted(self):
        import services.event_config_service as m

        for event_type in ("follow", "subscribe", "raid", "bits"):
            cfg = {**_EVENT_CONFIG, "event_type": event_type}
            with patch.object(m.EventConfigService, "update_config", AsyncMock(return_value=cfg)):
                r = _make_client().put(
                    f"/api/events/configs/{event_type}",
                    json={"message_template": "hi", "enabled": True},
                )
            assert r.status_code == 200, f"failed for {event_type}"

    def test_not_found_returns_404(self):
        import services.event_config_service as m

        with patch.object(m.EventConfigService, "update_config", AsyncMock(return_value=None)):
            r = _make_client().put(
                "/api/events/configs/follow",
                json={"message_template": "test", "enabled": True},
            )
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.event_config_service as m

        with patch.object(
            m.EventConfigService, "update_config", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().put(
                "/api/events/configs/follow",
                json={"message_template": "test", "enabled": True},
            )
        assert r.status_code == 500


# ── PATCH /api/events/configs/{event_type}/toggle ──


class TestToggleEventConfig:
    def test_toggles_config(self):
        import services.event_config_service as m

        toggled = {**_EVENT_CONFIG, "enabled": False}
        with patch.object(m.EventConfigService, "toggle_config", AsyncMock(return_value=toggled)):
            r = _make_client().patch("/api/events/configs/follow/toggle", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_invalid_event_type_returns_400(self):
        r = _make_client().patch("/api/events/configs/bad_type/toggle", json={"enabled": True})
        assert r.status_code == 400

    def test_not_found_returns_404(self):
        import services.event_config_service as m

        with patch.object(m.EventConfigService, "toggle_config", AsyncMock(return_value=None)):
            r = _make_client().patch("/api/events/configs/follow/toggle", json={"enabled": True})
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.event_config_service as m

        with patch.object(
            m.EventConfigService, "toggle_config", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().patch("/api/events/configs/follow/toggle", json={"enabled": True})
        assert r.status_code == 500


# ── GET /api/events/twitch-rewards ──


class TestGetTwitchRewards:
    def test_returns_rewards_for_affiliate(self):
        import services.channel_service as cs

        mock_api = MagicMock()
        mock_api.get_user_info = AsyncMock(return_value={"broadcaster_type": "affiliate"})
        mock_api.get_custom_rewards = AsyncMock(return_value=[_REWARD])

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="tok")
        ):
            r = _make_client(mock_twitch_api=mock_api).get("/api/events/twitch-rewards")
        assert r.status_code == 200
        assert r.json()[0]["title"] == "VIP"

    def test_returns_rewards_for_partner(self):
        import services.channel_service as cs

        mock_api = MagicMock()
        mock_api.get_user_info = AsyncMock(return_value={"broadcaster_type": "partner"})
        mock_api.get_custom_rewards = AsyncMock(return_value=[_REWARD])

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="tok")
        ):
            r = _make_client(mock_twitch_api=mock_api).get("/api/events/twitch-rewards")
        assert r.status_code == 200

    def test_non_affiliate_returns_403(self):
        mock_api = MagicMock()
        mock_api.get_user_info = AsyncMock(return_value={"broadcaster_type": ""})
        r = _make_client(mock_twitch_api=mock_api).get("/api/events/twitch-rewards")
        assert r.status_code == 403

    def test_missing_user_info_returns_403(self):
        mock_api = MagicMock()
        mock_api.get_user_info = AsyncMock(return_value=None)
        r = _make_client(mock_twitch_api=mock_api).get("/api/events/twitch-rewards")
        assert r.status_code == 403

    def test_no_token_returns_401(self):
        import services.channel_service as cs

        mock_api = MagicMock()
        mock_api.get_user_info = AsyncMock(return_value={"broadcaster_type": "partner"})

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value=None)
        ):
            r = _make_client(mock_twitch_api=mock_api).get("/api/events/twitch-rewards")
        assert r.status_code == 401

    def test_exception_returns_500(self):
        mock_api = MagicMock()
        mock_api.get_user_info = AsyncMock(side_effect=RuntimeError("network"))
        r = _make_client(mock_twitch_api=mock_api).get("/api/events/twitch-rewards")
        assert r.status_code == 500


# ── GET /api/events/redemptions ──


class TestGetRedemptionConfigs:
    def test_returns_redemptions(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "list_redemptions", AsyncMock(return_value=[_REDEMPTION])
        ):
            r = _make_client().get("/api/events/redemptions")
        assert r.status_code == 200
        assert r.json()[0]["action_type"] == "vip"

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "list_redemptions", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().get("/api/events/redemptions")
        assert r.status_code == 500


# ── PUT /api/events/redemptions/{action_type} ──


class TestUpdateRedemptionConfig:
    def test_updates_redemption(self):
        import services.command_config_service as m

        updated = {**_REDEMPTION, "reward_name": "New Reward"}
        with patch.object(
            m.CommandConfigService, "update_redemption", AsyncMock(return_value=updated)
        ):
            r = _make_client().put(
                "/api/events/redemptions/vip",
                json={"reward_name": "New Reward", "enabled": True},
            )
        assert r.status_code == 200
        assert r.json()["reward_name"] == "New Reward"

    def test_invalid_action_type_returns_400(self):
        r = _make_client().put(
            "/api/events/redemptions/invalid_action",
            json={"reward_name": "test", "enabled": True},
        )
        assert r.status_code == 400

    def test_all_valid_action_types_accepted(self):
        import services.command_config_service as m

        for action_type in ("vip", "first", "niibot_auth", "game_queue", "video_queue"):
            cfg = {**_REDEMPTION, "action_type": action_type}
            with patch.object(
                m.CommandConfigService, "update_redemption", AsyncMock(return_value=cfg)
            ):
                r = _make_client().put(
                    f"/api/events/redemptions/{action_type}",
                    json={"reward_name": "test", "enabled": True},
                )
            assert r.status_code == 200, f"failed for {action_type}"

    def test_not_found_returns_404(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "update_redemption", AsyncMock(return_value=None)
        ):
            r = _make_client().put(
                "/api/events/redemptions/vip",
                json={"reward_name": "test", "enabled": True},
            )
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "update_redemption", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().put(
                "/api/events/redemptions/vip",
                json={"reward_name": "test", "enabled": True},
            )
        assert r.status_code == 500
