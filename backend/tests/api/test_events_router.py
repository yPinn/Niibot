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
from core.error_handlers import register_exception_handlers
from routers.events_router import router as _events_router
from shared.events import EVENT_KEYS

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
    "reward_id": "r-1",
    "enabled": True,
    "first_message": "$(@user) 恭喜你搶到沙發！",
    "first_announce_color": "primary",
    "created_at": None,
    "updated_at": None,
}

_REWARD = {
    "id": "r-1",
    "title": "VIP",
    "cost": 1000,
    "is_enabled": True,
    "is_paused": False,
    "is_in_stock": True,
    "should_redemptions_skip_request_queue": True,
    "max_per_stream": 100,
    "max_per_user_per_stream": 1,
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
    register_exception_handlers(app)
    app.include_router(_events_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    mock_api = mock_twitch_api or MagicMock()
    app.dependency_overrides[get_twitch_api] = lambda: mock_api
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/events/catalog ──


class TestGetEventCatalog:
    def test_returns_all_events_in_display_order(self):
        r = _make_client().get("/api/events/catalog")
        assert r.status_code == 200
        keys = [e["key"] for e in r.json()]
        assert keys == list(EVENT_KEYS)
        assert keys == [
            "follow",
            "subscribe",
            "resub",
            "gift_sub",
            "gift_recipient",
            "watch_streak",
            "bits",
            "raid",
        ]

    def test_watch_streak_exposes_shared_milestone_variables(self):
        r = _make_client().get("/api/events/catalog")
        by_key = {event["key"]: event for event in r.json()}

        event = by_key["watch_streak"]
        assert event["display_name"] == "連續觀看"
        assert [variable["name"] for variable in event["variables"]] == [
            "user",
            "@user",
            "streak",
            "points",
        ]
        assert event["default_enabled"] is False
        assert event["requires_affiliate"] is True

    def test_every_variable_has_a_preview_sample(self):
        r = _make_client().get("/api/events/catalog")
        for event in r.json():
            assert event["variables"], f"{event['key']}: no variables"
            for v in event["variables"]:
                assert v["sample"], f"{event['key']}.{v['name']}: empty sample"

    def test_raid_exposes_auto_shoutout_option_only(self):
        r = _make_client().get("/api/events/catalog")
        by_key = {e["key"]: e for e in r.json()}
        assert [o["key"] for o in by_key["raid"]["options_schema"]] == ["auto_shoutout"]
        assert by_key["bits"]["options_schema"] == []


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
        assert r.json()["error"]["code"] == "EVENT.INVALID"

    def test_all_valid_event_types_accepted(self):
        import services.event_config_service as m

        for event_type in EVENT_KEYS:
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
        assert r.json()[0]["max_per_stream"] == 100
        assert r.json()[0]["max_per_user_per_stream"] == 1
        assert r.json()[0]["should_redemptions_skip_request_queue"] is True

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

        updated = {**_REDEMPTION, "reward_name": "New Reward", "reward_id": "r-new"}
        with patch.object(
            m.CommandConfigService, "update_redemption", AsyncMock(return_value=updated)
        ) as service_mock:
            r = _make_client().put(
                "/api/events/redemptions/vip",
                json={"reward_name": "New Reward", "reward_id": "r-new", "enabled": True},
            )
        assert r.status_code == 200
        assert r.json()["reward_name"] == "New Reward"
        assert r.json()["reward_id"] == "r-new"

        service_mock.assert_awaited_once_with(
            CHANNEL_ID, "vip", "New Reward", True, reward_id="r-new"
        )

    def test_invalid_action_type_returns_400(self):
        r = _make_client().put(
            "/api/events/redemptions/invalid_action",
            json={"reward_name": "test", "enabled": True},
        )
        assert r.status_code == 400

    def test_rejects_oversized_reward_id_before_database_write(self):
        r = _make_client().put(
            "/api/events/redemptions/checkin",
            json={"reward_name": "每日簽到", "reward_id": "r" * 129, "enabled": True},
        )
        assert r.status_code == 422

    def test_all_valid_action_types_accepted(self):
        import services.command_config_service as m

        for action_type in (
            "vip",
            "first",
            "niibot_auth",
            "game_queue",
            "video_queue",
            "checkin",
        ):
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


# ── PUT /api/events/redemptions/first/settings ──


class TestUpdateFirstSettings:
    def test_updates_first_settings(self):
        import services.command_config_service as m

        updated = {
            **_REDEMPTION,
            "action_type": "first",
            "first_message": "$(user) 手速真快！",
            "first_announce_color": "green",
        }
        with patch.object(
            m.CommandConfigService, "update_first_settings", AsyncMock(return_value=updated)
        ) as service_mock:
            r = _make_client().put(
                "/api/events/redemptions/first/settings",
                json={"message": "$(user) 手速真快！", "announce_color": "green"},
            )
        assert r.status_code == 200
        assert r.json()["first_message"] == "$(user) 手速真快！"
        assert r.json()["first_announce_color"] == "green"

        service_mock.assert_awaited_once_with(
            CHANNEL_ID, message="$(user) 手速真快！", announce_color="green"
        )

    def test_rejects_oversized_message(self):
        r = _make_client().put(
            "/api/events/redemptions/first/settings",
            json={"message": "x" * 301, "announce_color": "primary"},
        )
        assert r.status_code == 422

    def test_rejects_empty_message(self):
        r = _make_client().put(
            "/api/events/redemptions/first/settings",
            json={"message": "", "announce_color": "primary"},
        )
        assert r.status_code == 422

    def test_rejects_unknown_color(self):
        r = _make_client().put(
            "/api/events/redemptions/first/settings",
            json={"message": "hi", "announce_color": "rainbow"},
        )
        assert r.status_code == 422

    def test_not_found_returns_404(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "update_first_settings", AsyncMock(return_value=None)
        ):
            r = _make_client().put(
                "/api/events/redemptions/first/settings",
                json={"message": "hi", "announce_color": "primary"},
            )
        assert r.status_code == 404

    def test_service_exception_returns_500(self):
        import services.command_config_service as m

        with patch.object(
            m.CommandConfigService, "update_first_settings", AsyncMock(side_effect=RuntimeError)
        ):
            r = _make_client().put(
                "/api/events/redemptions/first/settings",
                json={"message": "hi", "announce_color": "primary"},
            )
        assert r.status_code == 500
