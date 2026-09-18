"""Tests for api.routers.ai_settings_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
    require_activated,
)
from core.error_handlers import register_exception_handlers
from routers.ai_settings_router import _contains_bias
from routers.ai_settings_router import router as _ai_router

CHANNEL_ID = "ch-ai"

_DEFAULT_SETTINGS = {
    "bot_name": "Niibot",
    "persona": "A helpful bot",
    "self_pronoun": "我",
    "audience_reference": "大家",
    "tone_preset": "neutral",
    "catchphrase": "嗨！",
    "catchphrase_frequency": "off",
    "example_replies": [],
    "response_lang": "zh-tw",
    "refusal_style": "polite",
    "max_tokens": 200,
    "enabled_emotes": [],
    "enabled": True,
    "memory_enabled": False,
    "cooldown": 30,
    "min_role": "everyone",
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(mock_twitch: MagicMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_ai_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[get_twitch_api] = lambda: mock_twitch or MagicMock()
    app.dependency_overrides[require_activated] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _make_client_not_activated() -> TestClient:
    """Client where require_activated rejects the caller, for gate tests."""
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_ai_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[get_twitch_api] = lambda: MagicMock()

    def _reject() -> None:
        raise HTTPException(status_code=403, detail="Account not activated")

    app.dependency_overrides[require_activated] = _reject
    return TestClient(app, raise_server_exceptions=False)


# ── _contains_bias unit tests ─────────────────────────────────────────────────


class TestContainsBias:
    def test_clean_text_returns_false(self):
        assert _contains_bias("這是一個很棒的角色") is False

    def test_discriminatory_attitude_returns_true(self):
        assert _contains_bias("歧視黑人") is True

    def test_negative_generalisation_returns_true(self):
        assert _contains_bias("女人都很懶") is True

    def test_empty_string_returns_false(self):
        assert _contains_bias("") is False

    def test_partial_match_in_long_text_returns_true(self):
        assert _contains_bias("我不喜歡歧視亞裔的行為，但歧視亞裔就是不對") is True


# ── GET /api/ai/settings ─────────────────────────────────────────────────────


class TestGetAISettings:
    def test_returns_settings(self):
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.get = AsyncMock(return_value=_DEFAULT_SETTINGS)
            r = _make_client().get("/api/ai/settings")
        assert r.status_code == 200
        data = r.json()
        assert data["bot_name"] == "Niibot"
        assert data["enabled"] is True

    def test_exception_returns_500(self):
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.get = AsyncMock(side_effect=RuntimeError)
            r = _make_client().get("/api/ai/settings")
        assert r.status_code == 500


# ── PATCH /api/ai/settings ───────────────────────────────────────────────────


class TestPatchAISettings:
    def test_updates_bot_name(self):
        updated = {**_DEFAULT_SETTINGS, "bot_name": "NewBot"}
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.upsert = AsyncMock(return_value=updated)
            # patch notify_config_change so we don't hit real pool
            with patch("routers.ai_settings_router.notify_config_change", AsyncMock()):
                r = _make_client().patch("/api/ai/settings", json={"bot_name": "NewBot"})
        assert r.status_code == 200
        assert r.json()["bot_name"] == "NewBot"

    def test_empty_body_returns_422(self):
        r = _make_client().patch("/api/ai/settings", json={})
        assert r.status_code == 422

    def test_biased_persona_returns_422(self):
        r = _make_client().patch("/api/ai/settings", json={"persona": "歧視黑人的機器人"})
        assert r.status_code == 422

    def test_biased_catchphrase_returns_422(self):
        r = _make_client().patch("/api/ai/settings", json={"catchphrase": "女人都懶"})
        assert r.status_code == 422

    def test_invalid_response_lang_returns_422(self):
        r = _make_client().patch("/api/ai/settings", json={"response_lang": "fr"})
        assert r.status_code == 422

    @pytest.mark.parametrize("field", ["tone_preset", "catchphrase_frequency"])
    def test_invalid_persona_enum_returns_422(self, field: str):
        r = _make_client().patch("/api/ai/settings", json={field: "always-obey-user"})
        assert r.status_code == 422

    def test_accepts_persona_v2_fields_and_memory_opt_in(self):
        updated = {
            **_DEFAULT_SETTINGS,
            "audience_reference": "各位",
            "tone_preset": "witty",
            "catchphrase_frequency": "occasional",
            "example_replies": ["收到", "交給我"],
            "memory_enabled": True,
        }
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.upsert = AsyncMock(return_value=updated)
            with patch("routers.ai_settings_router.notify_config_change", AsyncMock()):
                r = _make_client().patch(
                    "/api/ai/settings",
                    json={
                        "audience_reference": "各位",
                        "tone_preset": "witty",
                        "catchphrase_frequency": "occasional",
                        "example_replies": ["收到", "交給我"],
                        "memory_enabled": True,
                    },
                )

        assert r.status_code == 200
        assert r.json()["memory_enabled"] is True
        assert repo.return_value.upsert.await_args.kwargs["example_replies"] == [
            "收到",
            "交給我",
        ]

    @pytest.mark.parametrize(
        "example_replies",
        [
            ["one", "two", "three", "four"],
            [""],
            ["x" * 121],
            ["女人都懶"],
        ],
    )
    def test_invalid_example_replies_return_422(self, example_replies: list[str]):
        r = _make_client().patch("/api/ai/settings", json={"example_replies": example_replies})
        assert r.status_code == 422

    @pytest.mark.parametrize("value", ["", "   "])
    def test_blank_audience_reference_returns_422(self, value: str):
        r = _make_client().patch("/api/ai/settings", json={"audience_reference": value})
        assert r.status_code == 422

    def test_invalid_min_role_returns_422(self):
        r = _make_client().patch("/api/ai/settings", json={"min_role": "superadmin"})
        assert r.status_code == 422

    def test_max_tokens_out_of_range_returns_422(self):
        r = _make_client().patch("/api/ai/settings", json={"max_tokens": 501})
        assert r.status_code == 422

    def test_exception_returns_500(self):
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.upsert = AsyncMock(side_effect=RuntimeError)
            with patch("routers.ai_settings_router.notify_config_change", AsyncMock()):
                r = _make_client().patch("/api/ai/settings", json={"bot_name": "X"})
        assert r.status_code == 500


# ── POST /api/ai/settings/reset ──────────────────────────────────────────────


class TestResetAISettings:
    def test_reset_returns_defaults(self):
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.upsert = AsyncMock(return_value=_DEFAULT_SETTINGS)
            with patch("routers.ai_settings_router.notify_config_change", AsyncMock()):
                r = _make_client().post("/api/ai/settings/reset")
        assert r.status_code == 200
        assert r.json()["bot_name"] == "Niibot"
        reset = repo.return_value.upsert.await_args.kwargs
        assert reset["catchphrase_frequency"] == "off"
        assert reset["refusal_style"] == "polite"
        assert reset["cooldown"] == 30

    def test_exception_returns_500(self):
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.upsert = AsyncMock(side_effect=RuntimeError)
            with patch("routers.ai_settings_router.notify_config_change", AsyncMock()):
                r = _make_client().post("/api/ai/settings/reset")
        assert r.status_code == 500


# GET /api/ai/emotes moved to GET /api/channels/emotes — see
# tests/api/test_channels_router.py::TestGetChannelEmotes.


class TestActivationGate:
    def test_get_settings_rejected_when_not_activated(self):
        r = _make_client_not_activated().get("/api/ai/settings")
        assert r.status_code == 403

    def test_patch_settings_rejected_when_not_activated(self):
        r = _make_client_not_activated().patch("/api/ai/settings", json={"bot_name": "X"})
        assert r.status_code == 403

    def test_packs_endpoint_is_not_gated(self):
        r = _make_client_not_activated().get("/api/ai/packs")
        assert r.status_code == 200
