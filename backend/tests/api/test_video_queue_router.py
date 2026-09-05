"""Tests for api.routers.video_queue_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    VIDEO_QUEUE_NOTIFY_CHANNEL,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
    require_activated,
)
from core.error_handlers import register_exception_handlers
from routers.video_queue_router import router as _vq_router
from routers.video_queue_router import stream_public_video_queue
from services.notify_stream import NotifyWakeHub

CHANNEL_ID = "ch-vq"


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_settings(**kw) -> MagicMock:
    s = MagicMock()
    s.channel_id = CHANNEL_ID
    s.enabled = kw.get("enabled", True)
    s.redemption_enabled = kw.get("redemption_enabled", True)
    s.max_duration_redemption = kw.get("max_duration_redemption", 600)
    s.max_queue_size = kw.get("max_queue_size", 10)
    s.min_view_count = kw.get("min_view_count", 0)
    s.user_cooldown_seconds = kw.get("user_cooldown_seconds", 0)
    s.max_per_user = kw.get("max_per_user", 5)
    return s


def _make_entry(**kw) -> MagicMock:
    e = MagicMock()
    e.id = kw.get("id", 1)
    e.video_id = kw.get("video_id", "dQw4w9WgXcQ")
    e.title = kw.get("title", "Test Video")
    e.duration_seconds = kw.get("duration_seconds", 213)
    e.is_vertical = kw.get("is_vertical", False)
    e.requested_by = kw.get("requested_by", "streamer")
    e.source = kw.get("source", "dashboard")
    e.video_type = kw.get("video_type", "youtube")
    e.started_at = kw.get("started_at", None)
    return e


def _make_public_client(twitch_api: MagicMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_vq_router)
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[get_twitch_api] = lambda: twitch_api or MagicMock()
    return TestClient(app, raise_server_exceptions=False)


def _make_auth_client() -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_vq_router)
    app.dependency_overrides[require_activated] = lambda: None
    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    return TestClient(app, raise_server_exceptions=False)


def _twitch_api_found() -> MagicMock:
    api = MagicMock()
    api.get_user_by_login = AsyncMock(return_value={"id": CHANNEL_ID})
    return api


def _twitch_api_not_found() -> MagicMock:
    api = MagicMock()
    api.get_user_by_login = AsyncMock(return_value=None)
    return api


# ── GET /api/video-queue/public/{username} ────────────────────────────────────


class TestGetPublicState:
    def test_empty_queue(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_public_client(_twitch_api_found()).get("/api/video-queue/public/testuser")
        assert r.status_code == 200
        data = r.json()
        assert data["current"] is None
        assert data["queue"] == []
        assert data["queue_size"] == 0
        assert data["enabled"] is True

    def test_with_current_and_queued(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.get_current = AsyncMock(return_value=_make_entry())
            vqr.return_value.get_queued = AsyncMock(return_value=[_make_entry(id=2)])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_public_client(_twitch_api_found()).get("/api/video-queue/public/testuser")
        assert r.status_code == 200
        data = r.json()
        assert data["current"]["id"] == 1
        assert data["current"]["video_id"] == "dQw4w9WgXcQ"
        assert len(data["queue"]) == 1
        assert data["queue_size"] == 1
        # queued entries never expose started_at (set to None by router)
        assert data["queue"][0]["started_at"] is None

    def test_total_queued_duration_sum(self):
        q = [_make_entry(id=2, duration_seconds=100), _make_entry(id=3, duration_seconds=200)]
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=q)
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_public_client(_twitch_api_found()).get("/api/video-queue/public/testuser")
        assert r.json()["total_queued_duration"] == 300

    def test_total_queued_duration_none_when_any_unknown(self):
        q = [_make_entry(id=2, duration_seconds=None), _make_entry(id=3, duration_seconds=200)]
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=q)
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_public_client(_twitch_api_found()).get("/api/video-queue/public/testuser")
        assert r.json()["total_queued_duration"] is None

    def test_channel_not_found_returns_404(self):
        r = _make_public_client(_twitch_api_not_found()).get("/api/video-queue/public/unknown")
        assert r.status_code == 404

    def test_repo_exception_returns_500(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(side_effect=RuntimeError("db"))
            r = _make_public_client(_twitch_api_found()).get("/api/video-queue/public/testuser")
        assert r.status_code == 500


# ── POST /api/video-queue/public/{username}/advance ───────────────────────────


class TestAdvanceQueue:
    def test_advance_with_done_id_calls_advance_queue(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.advance_queue = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_public_client(_twitch_api_found()).post(
                "/api/video-queue/public/testuser/advance", json={"done_id": 5}
            )
        assert r.status_code == 200
        vqr.return_value.advance_queue.assert_called_once_with(CHANNEL_ID, 5)

    def test_advance_without_done_id_kickstarts(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.kickstart_if_idle = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_public_client(_twitch_api_found()).post(
                "/api/video-queue/public/testuser/advance", json={}
            )
        assert r.status_code == 200
        vqr.return_value.kickstart_if_idle.assert_called_once_with(CHANNEL_ID)

    def test_channel_not_found_returns_404(self):
        r = _make_public_client(_twitch_api_not_found()).post(
            "/api/video-queue/public/unknown/advance", json={}
        )
        assert r.status_code == 404

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.kickstart_if_idle = AsyncMock(side_effect=RuntimeError)
            r = _make_public_client(_twitch_api_found()).post(
                "/api/video-queue/public/testuser/advance", json={}
            )
        assert r.status_code == 500


# ── PATCH /api/video-queue/public/{username}/entries/{entry_id}/metadata ──────


class TestUpdateEntryMetadata:
    def test_success_returns_204(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.update_duration = AsyncMock()
            r = _make_public_client(_twitch_api_found()).patch(
                "/api/video-queue/public/testuser/entries/1/metadata",
                json={"duration_seconds": 120},
            )
        assert r.status_code == 204

    def test_channel_not_found_returns_404(self):
        r = _make_public_client(_twitch_api_not_found()).patch(
            "/api/video-queue/public/unknown/entries/1/metadata",
            json={"duration_seconds": 120},
        )
        assert r.status_code == 404

    def test_zero_duration_returns_422(self):
        r = _make_public_client(_twitch_api_found()).patch(
            "/api/video-queue/public/testuser/entries/1/metadata",
            json={"duration_seconds": 0},
        )
        assert r.status_code == 422

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.update_duration = AsyncMock(side_effect=RuntimeError)
            r = _make_public_client(_twitch_api_found()).patch(
                "/api/video-queue/public/testuser/entries/1/metadata",
                json={"duration_seconds": 120},
            )
        assert r.status_code == 500


# ── DELETE /api/video-queue/skip ─────────────────────────────────────────────


class TestSkipCurrent:
    def test_skip_returns_state(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.skip_current_atomic = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().delete("/api/video-queue/skip")
        assert r.status_code == 200
        assert r.json()["queue_size"] == 0

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.skip_current_atomic = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().delete("/api/video-queue/skip")
        assert r.status_code == 500


# ── DELETE /api/video-queue/clear ────────────────────────────────────────────


class TestClearQueue:
    def test_clear_returns_empty_state(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.clear_all_atomic = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().delete("/api/video-queue/clear")
        assert r.status_code == 200
        assert r.json()["current"] is None

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.clear_all_atomic = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().delete("/api/video-queue/clear")
        assert r.status_code == 500


# ── GET /api/video-queue/settings ────────────────────────────────────────────


class TestGetVideoQueueSettings:
    def test_returns_settings(self):
        with patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr:
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().get("/api/video-queue/settings")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is True
        assert data["max_queue_size"] == 10
        assert data["channel_id"] == CHANNEL_ID

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr:
            sr.return_value.get_or_create = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().get("/api/video-queue/settings")
        assert r.status_code == 500


# ── PUT /api/video-queue/settings ────────────────────────────────────────────


class TestUpdateVideoQueueSettings:
    def test_updates_enabled_field(self):
        with patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr:
            sr.return_value.update_settings = AsyncMock(return_value=_make_settings(enabled=False))
            r = _make_auth_client().put("/api/video-queue/settings", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_no_fields_returns_400(self):
        r = _make_auth_client().put("/api/video-queue/settings", json={})
        assert r.status_code == 400

    def test_max_duration_below_min_returns_422(self):
        r = _make_auth_client().put(
            "/api/video-queue/settings", json={"max_duration_redemption": 29}
        )
        assert r.status_code == 422

    def test_max_queue_size_above_max_returns_422(self):
        r = _make_auth_client().put("/api/video-queue/settings", json={"max_queue_size": 101})
        assert r.status_code == 422

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr:
            sr.return_value.update_settings = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().put("/api/video-queue/settings", json={"enabled": True})
        assert r.status_code == 500


# ── GET /api/video-queue/state ───────────────────────────────────────────────


class TestGetState:
    def test_returns_current_state(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.get_current = AsyncMock(return_value=_make_entry())
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().get("/api/video-queue/state")
        assert r.status_code == 200
        assert r.json()["current"]["video_id"] == "dQw4w9WgXcQ"

    def test_exception_returns_500(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            vqr.return_value.get_current = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().get("/api/video-queue/state")
        assert r.status_code == 500


# ── POST /api/video-queue/entries/{entry_id}/set-next ────────────────────────


class TestSetEntryAsNext:
    def test_success(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.set_as_next = AsyncMock(return_value=True)
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().post("/api/video-queue/entries/1/set-next")
        assert r.status_code == 200

    def test_not_found_returns_404(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.set_as_next = AsyncMock(return_value=False)
            r = _make_auth_client().post("/api/video-queue/entries/99/set-next")
        assert r.status_code == 404

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.set_as_next = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().post("/api/video-queue/entries/1/set-next")
        assert r.status_code == 500


# ── POST /api/video-queue/entries/{entry_id}/play-now ────────────────────────


class TestPlayEntryNow:
    def test_success(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.play_immediately = AsyncMock(return_value=True)
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().post("/api/video-queue/entries/1/play-now")
        assert r.status_code == 200

    def test_not_found_returns_404(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.play_immediately = AsyncMock(return_value=False)
            r = _make_auth_client().post("/api/video-queue/entries/99/play-now")
        assert r.status_code == 404

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.play_immediately = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().post("/api/video-queue/entries/1/play-now")
        assert r.status_code == 500


# ── DELETE /api/video-queue/entries/{entry_id} ───────────────────────────────


class TestRemoveQueueEntry:
    def test_removes_entry(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.mark_skipped = AsyncMock(return_value=True)
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().delete("/api/video-queue/entries/1")
        assert r.status_code == 200

    def test_not_found_returns_404(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.mark_skipped = AsyncMock(return_value=False)
            r = _make_auth_client().delete("/api/video-queue/entries/99")
        assert r.status_code == 404

    def test_exception_returns_500(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.mark_skipped = AsyncMock(side_effect=RuntimeError)
            r = _make_auth_client().delete("/api/video-queue/entries/1")
        assert r.status_code == 500


# ── POST /api/video-queue/entries ────────────────────────────────────────────


class TestAddVideoEntry:
    def test_add_youtube_video_returns_201(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=("vid123", False),
            ),
            patch(
                "routers.video_queue_router.fetch_yt_info",
                AsyncMock(return_value=("YT Title", 300, None, False)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
            patch("routers.video_queue_router.ChannelRepository") as cr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            vqr.return_value.add = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            cr.return_value.get_broadcaster_display_name = AsyncMock(return_value="Streamer")
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 201

    def test_add_twitch_clip_returns_201(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=(None, False),
            ),
            patch(
                "routers.video_queue_router.extract_twitch_clip_slug",
                return_value="AwesomeClip",
            ),
            patch(
                "routers.video_queue_router.fetch_twitch_clip_info",
                AsyncMock(return_value=("Clip Title", 60, None)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
            patch("routers.video_queue_router.ChannelRepository") as cr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            vqr.return_value.add = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            cr.return_value.get_broadcaster_display_name = AsyncMock(return_value="Streamer")
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://clips.twitch.tv/AwesomeClip"},
            )
        assert r.status_code == 201

    def test_add_bilibili_video_returns_201(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=(None, False),
            ),
            patch(
                "routers.video_queue_router.extract_twitch_clip_slug",
                return_value=None,
            ),
            patch(
                "routers.video_queue_router.resolve_bilibili_url",
                AsyncMock(return_value="BV1test"),
            ),
            patch(
                "routers.video_queue_router.fetch_bilibili_info",
                AsyncMock(return_value=("BV Title", 200, None, True)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
            patch("routers.video_queue_router.ChannelRepository") as cr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            vqr.return_value.add = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            cr.return_value.get_broadcaster_display_name = AsyncMock(return_value=None)
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://bilibili.com/video/BV1test"},
            )
        assert r.status_code == 201

    def test_invalid_url_returns_422(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=(None, False),
            ),
            patch(
                "routers.video_queue_router.extract_twitch_clip_slug",
                return_value=None,
            ),
            patch(
                "routers.video_queue_router.resolve_bilibili_url",
                AsyncMock(return_value=None),
            ),
        ):
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://example.com/not-a-video"},
            )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VIDEO_QUEUE.INVALID_URL"

    def test_queue_disabled_returns_403(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=("vid123", False),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings(enabled=False))
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 403

    def test_duplicate_video_returns_409(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=("vid123", False),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            vqr.return_value.video_is_active = AsyncMock(return_value=True)
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 409

    def test_repo_exception_returns_500(self):
        with (
            patch(
                "routers.video_queue_router.extract_youtube_info",
                return_value=("vid123", False),
            ),
            patch(
                "routers.video_queue_router.fetch_yt_info",
                AsyncMock(return_value=("Title", 300, None, False)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
            patch("routers.video_queue_router.ChannelRepository") as cr,
        ):
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            vqr.return_value.add = AsyncMock(side_effect=RuntimeError("db error"))
            cr.return_value.get_broadcaster_display_name = AsyncMock(return_value="Streamer")
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 500


# ── GET /api/video-queue/public/{username}/stream ─────────────────────────────


def _make_request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/video-queue/public/testuser/stream",
            "headers": [],
            "client": (host, 1234),
        }
    )


def _hub(**kwargs: object) -> NotifyWakeHub:
    return NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[VIDEO_QUEUE_NOTIFY_CHANNEL],
        **kwargs,
    )


class TestStreamPublicVideoQueue:
    def test_snapshot_frame_has_no_enabled_field(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(return_value=(_make_entry(), []))
            hub = _hub()

            async def run():
                response = await stream_public_video_queue(
                    request=_make_request("127.0.10.1"),
                    username="testuser",
                    pool=AsyncMock(),
                    twitch_api=_twitch_api_found(),
                    hub=hub,
                )
                frame = await anext(response.body_iterator)
                await response.body_iterator.aclose()
                return response, frame

            response, frame = asyncio.run(run())

        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-store, no-transform"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-accel-buffering"] == "no"
        assert frame.startswith("event: snapshot\n")
        assert '"id":1' in frame
        assert "enabled" not in frame

    def test_update_frame_sent_when_state_changes(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(
                side_effect=[
                    (_make_entry(id=1), []),
                    (_make_entry(id=2), []),
                ]
            )
            hub = _hub()

            async def run():
                response = await stream_public_video_queue(
                    request=_make_request("127.0.10.2"),
                    username="testuser",
                    pool=AsyncMock(),
                    twitch_api=_twitch_api_found(),
                    hub=hub,
                )
                await anext(response.body_iterator)  # snapshot
                hub.notify(VIDEO_QUEUE_NOTIFY_CHANNEL, CHANNEL_ID)
                frame = await asyncio.wait_for(anext(response.body_iterator), timeout=1.0)
                await response.body_iterator.aclose()
                return frame

            frame = asyncio.run(run())

        assert frame.startswith("event: update\n")
        assert '"id":2' in frame

    def test_no_frame_sent_when_rebuild_is_identical(self):
        """The dedup compare exists to suppress rebuild noise from unrelated
        wakes (e.g. reconnect notify_all()) — an identical rebuild must not
        emit a frame, only a genuinely different one should."""
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(
                side_effect=[
                    (_make_entry(id=1), []),
                    (_make_entry(id=1), []),  # identical rebuild — must be suppressed
                    (_make_entry(id=2), []),
                ]
            )
            hub = _hub()

            async def run():
                response = await stream_public_video_queue(
                    request=_make_request("127.0.10.3"),
                    username="testuser",
                    pool=AsyncMock(),
                    twitch_api=_twitch_api_found(),
                    hub=hub,
                )
                await anext(response.body_iterator)  # snapshot

                next_frame = asyncio.ensure_future(anext(response.body_iterator))
                hub.notify(VIDEO_QUEUE_NOTIFY_CHANNEL, CHANNEL_ID)  # identical rebuild
                await asyncio.sleep(0.05)  # let the generator loop past the no-op
                assert not next_frame.done()
                hub.notify(VIDEO_QUEUE_NOTIFY_CHANNEL, CHANNEL_ID)  # real change
                frame = await asyncio.wait_for(next_frame, timeout=1.0)
                await response.body_iterator.aclose()
                return frame

            frame = asyncio.run(run())

        assert frame.startswith("event: update\n")
        assert '"id":2' in frame

    def test_heartbeat_sent_when_idle(self, monkeypatch):
        monkeypatch.setattr("routers.video_queue_router._STREAM_HEARTBEAT_SECONDS", 0.01)
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(return_value=(None, []))
            hub = _hub()

            async def run():
                response = await stream_public_video_queue(
                    request=_make_request("127.0.10.4"),
                    username="testuser",
                    pool=AsyncMock(),
                    twitch_api=_twitch_api_found(),
                    hub=hub,
                )
                await anext(response.body_iterator)  # snapshot
                frame = await asyncio.wait_for(anext(response.body_iterator), timeout=1.0)
                await response.body_iterator.aclose()
                return frame

            frame = asyncio.run(run())

        assert frame.startswith("event: heartbeat\n")

    def test_hard_lease_releases_subscription(self, monkeypatch):
        monkeypatch.setattr("routers.video_queue_router._STREAM_LEASE_SECONDS", 0.01)
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(return_value=(None, []))
            hub = _hub()

            async def run():
                response = await stream_public_video_queue(
                    request=_make_request("127.0.10.5"),
                    username="testuser",
                    pool=AsyncMock(),
                    twitch_api=_twitch_api_found(),
                    hub=hub,
                )
                await anext(response.body_iterator)
                assert hub.subscriber_count == 1
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(anext(response.body_iterator), timeout=0.2)
                return hub

            hub = asyncio.run(run())

        assert hub.subscriber_count == 0

    def test_capacity_exhaustion_returns_429(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(return_value=(None, []))
            hub = _hub(max_subscribers_per_channel=1)
            hub.subscribe(VIDEO_QUEUE_NOTIFY_CHANNEL, CHANNEL_ID)

            async def run():
                with pytest.raises(HTTPException) as exc_info:
                    await stream_public_video_queue(
                        request=_make_request("127.0.10.6"),
                        username="testuser",
                        pool=AsyncMock(),
                        twitch_api=_twitch_api_found(),
                        hub=hub,
                    )
                return exc_info.value

            exc = asyncio.run(run())

        assert exc.status_code == 429

    def test_releases_capacity_when_initial_state_build_fails(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_current_and_queued = AsyncMock(
                side_effect=RuntimeError("database unavailable")
            )
            hub = _hub()

            async def run():
                with pytest.raises(RuntimeError, match="database unavailable"):
                    await stream_public_video_queue(
                        request=_make_request("127.0.10.7"),
                        username="testuser",
                        pool=AsyncMock(),
                        twitch_api=_twitch_api_found(),
                        hub=hub,
                    )
                return hub

            hub = asyncio.run(run())

        assert hub.subscriber_count == 0

    def test_unknown_username_returns_404_without_subscribing(self):
        hub = _hub()

        async def run():
            with pytest.raises(HTTPException) as exc_info:
                await stream_public_video_queue(
                    request=_make_request("127.0.10.8"),
                    username="unknown",
                    pool=AsyncMock(),
                    twitch_api=_twitch_api_not_found(),
                    hub=hub,
                )
            return exc_info.value

        exc = asyncio.run(run())

        assert exc.status_code == 404
        assert hub.subscriber_count == 0
