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
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from routers.ai_settings_router import _contains_bias
from routers.ai_settings_router import router as _ai_router

CHANNEL_ID = "ch-ai"

_DEFAULT_SETTINGS = {
    "bot_name": "Niibot",
    "persona": "A helpful bot",
    "self_pronoun": "我",
    "catchphrase": "嗨！",
    "response_lang": "zh-tw",
    "refusal_style": "humorous",
    "max_tokens": 200,
    "enabled_emotes": [],
    "enabled": True,
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
    app.include_router(_ai_router)
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[get_twitch_api] = lambda: mock_twitch or MagicMock()
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

    def test_exception_returns_500(self):
        with patch("routers.ai_settings_router.AISettingsRepository") as repo:
            repo.return_value.upsert = AsyncMock(side_effect=RuntimeError)
            with patch("routers.ai_settings_router.notify_config_change", AsyncMock()):
                r = _make_client().post("/api/ai/settings/reset")
        assert r.status_code == 500


# ── GET /api/ai/emotes ───────────────────────────────────────────────────────


class TestGetAIEmotes:
    def _make_emote(self, eid: str, name: str, etype: str = "globals") -> dict:
        return {
            "id": eid,
            "name": name,
            "url": f"https://cdn.example.com/{eid}.png",
            "emote_type": etype,
            "tier": "",
            "animated": False,
        }

    def test_returns_global_and_channel_emotes_without_bot_token(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(
            return_value=[self._make_emote("g1", "PogChamp", "globals")]
        )
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[self._make_emote("c1", "Kappa", "subscriptions")]
        )

        with (
            patch("routers.ai_settings_router.ChannelRepository") as cr,
            patch("routers.ai_settings_router._sync_emotes", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(mock_twitch).get("/api/ai/emotes")

        assert r.status_code == 200
        names = {e["name"] for e in r.json()}
        assert "PogChamp" in names
        assert "Kappa" in names

    def test_globals_and_follower_emotes_are_always_available(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(
            return_value=[self._make_emote("g1", "PogChamp", "globals")]
        )
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[self._make_emote("f1", "FollowEmote", "follower")]
        )

        with (
            patch("routers.ai_settings_router.ChannelRepository") as cr,
            patch("routers.ai_settings_router._sync_emotes", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(mock_twitch).get("/api/ai/emotes")

        emotes = {e["name"]: e for e in r.json()}
        assert emotes["PogChamp"]["available"] is True
        assert emotes["FollowEmote"]["available"] is True

    def test_sub_emote_available_when_bot_has_access(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[])
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[self._make_emote("s1", "SubEmote", "subscriptions")]
        )
        mock_twitch.get_user_emotes = AsyncMock(
            return_value=[self._make_emote("s1", "SubEmote", "subscriptions")]
        )

        token_row = MagicMock()
        token_row.token = "bot-token"

        with (
            patch("routers.ai_settings_router.ChannelRepository") as cr,
            patch("routers.ai_settings_router._sync_emotes", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=token_row)
            r = _make_client(mock_twitch).get("/api/ai/emotes")

        emotes = {e["name"]: e for e in r.json()}
        assert emotes["SubEmote"]["available"] is True

    def test_exception_returns_500(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(side_effect=RuntimeError("api error"))
        mock_twitch.get_channel_emotes = AsyncMock(return_value=[])

        with patch("routers.ai_settings_router.ChannelRepository") as cr:
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(mock_twitch).get("/api/ai/emotes")

        assert r.status_code == 500
