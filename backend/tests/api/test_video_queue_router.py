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
from datetime import UTC, datetime
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
from shared.models.video_queue import VideoQueueBlocklistEntry, VideoQueueEntry
from shared.video_sources import ResolvedVideo, VideoMetadata

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
    s.max_duration_seconds = kw.get("max_duration_seconds", 0)
    s.replay_cooldown_hours = kw.get("replay_cooldown_hours", 0)
    return s


def _make_entry(**kw) -> MagicMock:
    e = MagicMock()
    e.id = kw.get("id", 1)
    e.video_id = kw.get("video_id", "dQw4w9WgXcQ")
    e.title = kw.get("title", "Test Video")
    e.duration_seconds = kw.get("duration_seconds", 213)
    e.is_vertical = kw.get("is_vertical", False)
    e.start_seconds = kw.get("start_seconds", 0)
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


# ── GET /api/video-queue/public/{username}/entries/{id}/clip-source ───────────


class TestGetClipSource:
    _URL = "/api/video-queue/public/testuser/entries/5/clip-source"

    def test_returns_signed_url(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch(
                "routers.video_queue_router.fetch_twitch_clip_source",
                AsyncMock(return_value="https://cdn/clip.mp4?sig=a&token=b"),
            ),
        ):
            vqr.return_value.get_entry_for_channel = AsyncMock(
                return_value=_make_entry(id=5, video_type="twitch_clip", video_id="Slug")
            )
            r = _make_public_client(_twitch_api_found()).get(self._URL)
        assert r.status_code == 200
        assert r.json()["url"] == "https://cdn/clip.mp4?sig=a&token=b"

    def test_non_clip_entry_returns_404(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_entry_for_channel = AsyncMock(
                return_value=_make_entry(id=5, video_type="youtube")
            )
            r = _make_public_client(_twitch_api_found()).get(self._URL)
        assert r.status_code == 404

    def test_entry_not_found_returns_404(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_entry_for_channel = AsyncMock(return_value=None)
            r = _make_public_client(_twitch_api_found()).get(self._URL)
        assert r.status_code == 404

    def test_unresolvable_source_returns_404(self):
        with (
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch(
                "routers.video_queue_router.fetch_twitch_clip_source",
                AsyncMock(return_value=None),
            ),
        ):
            vqr.return_value.get_entry_for_channel = AsyncMock(
                return_value=_make_entry(id=5, video_type="twitch_clip", video_id="Slug")
            )
            r = _make_public_client(_twitch_api_found()).get(self._URL)
        assert r.status_code == 404

    def test_channel_not_found_returns_404(self):
        r = _make_public_client(_twitch_api_not_found()).get(
            "/api/video-queue/public/unknown/entries/5/clip-source"
        )
        assert r.status_code == 404


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

    def test_updates_gate_fields(self):
        with patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr:
            sr.return_value.update_settings = AsyncMock(
                return_value=_make_settings(max_duration_seconds=900, replay_cooldown_hours=6)
            )
            r = _make_auth_client().put(
                "/api/video-queue/settings",
                json={"max_duration_seconds": 900, "replay_cooldown_hours": 6},
            )
        assert r.status_code == 200
        assert r.json()["max_duration_seconds"] == 900
        assert r.json()["replay_cooldown_hours"] == 6
        kwargs = sr.return_value.update_settings.await_args.kwargs
        assert kwargs["max_duration_seconds"] == 900
        assert kwargs["replay_cooldown_hours"] == 6

    def test_replay_cooldown_above_max_returns_422(self):
        r = _make_auth_client().put(
            "/api/video-queue/settings", json={"replay_cooldown_hours": 169}
        )
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


# ── GET /api/video-queue/history ─────────────────────────────────────────────


def _history_entry(**kw) -> VideoQueueEntry:
    base = dict(
        id=1,
        channel_id=CHANNEL_ID,
        video_id="vid1",
        requested_by="viewer",
        source="chat",
        status="done",
        video_type="youtube",
        title="Watched",
        duration_seconds=120,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
    )
    base.update(kw)
    return VideoQueueEntry(**base)


class TestGetHistory:
    def test_returns_entries_and_no_cursor_when_page_not_full(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_history = AsyncMock(
                return_value=[_history_entry(id=2, status="skipped")]
            )
            r = _make_auth_client().get("/api/video-queue/history?limit=50")
        assert r.status_code == 200
        body = r.json()
        assert body["entries"][0]["status"] == "skipped"
        assert body["next_cursor"] is None

    def test_full_page_yields_cursor_from_last_ended_at(self):
        entries = [_history_entry(id=i) for i in range(2)]
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_history = AsyncMock(return_value=entries)
            r = _make_auth_client().get("/api/video-queue/history?limit=2")
        assert r.json()["next_cursor"] == entries[-1].ended_at.isoformat()

    def test_invalid_cursor_returns_422(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_history = AsyncMock(return_value=[])
            r = _make_auth_client().get("/api/video-queue/history?cursor=not-a-date")
        assert r.status_code == 422

    def test_cursor_parsed_and_passed_through(self):
        with patch("routers.video_queue_router.VideoQueueRepository") as vqr:
            vqr.return_value.get_history = AsyncMock(return_value=[])
            _make_auth_client().get("/api/video-queue/history?cursor=2026-01-01T00:00:00%2B00:00")
            kwargs = vqr.return_value.get_history.await_args.kwargs
            assert kwargs["before"] == datetime(2026, 1, 1, tzinfo=UTC)


# ── /api/video-queue/blocklist ──────────────────────────────────────────────


def _blocklist_entry(**kw) -> VideoQueueBlocklistEntry:
    return VideoQueueBlocklistEntry(
        id=kw.get("id", 1),
        channel_id=CHANNEL_ID,
        kind=kw.get("kind", "video"),
        value=kw.get("value", "vid123"),
        label=kw.get("label", "A video"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class TestBlocklistEndpoints:
    def test_list_returns_entries(self):
        with patch("routers.video_queue_router.VideoQueueBlocklistRepository") as bl:
            bl.return_value.list_entries = AsyncMock(
                return_value=[_blocklist_entry(kind="keyword", value="lofi")]
            )
            r = _make_auth_client().get("/api/video-queue/blocklist")
        assert r.status_code == 200
        assert r.json()[0] == {
            "id": 1,
            "kind": "keyword",
            "value": "lofi",
            "label": "A video",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_add_creates_entry(self):
        with patch("routers.video_queue_router.VideoQueueBlocklistRepository") as bl:
            bl.return_value.add = AsyncMock(return_value=_blocklist_entry(kind="user", value="bob"))
            r = _make_auth_client().post(
                "/api/video-queue/blocklist", json={"kind": "user", "value": "bob"}
            )
        assert r.status_code == 201
        assert bl.return_value.add.await_args.args == (CHANNEL_ID, "user", "bob")

    def test_add_rejects_unknown_kind(self):
        r = _make_auth_client().post(
            "/api/video-queue/blocklist", json={"kind": "channel", "value": "x"}
        )
        assert r.status_code == 422

    def test_add_rejects_creator_kind_for_now(self):
        r = _make_auth_client().post(
            "/api/video-queue/blocklist", json={"kind": "creator", "value": "x"}
        )
        assert r.status_code == 422

    def test_delete_missing_returns_404(self):
        with patch("routers.video_queue_router.VideoQueueBlocklistRepository") as bl:
            bl.return_value.remove = AsyncMock(return_value=False)
            r = _make_auth_client().delete("/api/video-queue/blocklist/9")
        assert r.status_code == 404

    def test_delete_success_returns_204(self):
        with patch("routers.video_queue_router.VideoQueueBlocklistRepository") as bl:
            bl.return_value.remove = AsyncMock(return_value=True)
            r = _make_auth_client().delete("/api/video-queue/blocklist/9")
        assert r.status_code == 204


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
    @pytest.fixture(autouse=True)
    def _stub_blocklist(self):
        """Every add path checks the blocklist; default it to "not blocked"."""
        with patch("routers.video_queue_router.VideoQueueBlocklistRepository") as bl:
            bl.return_value.check = AsyncMock(return_value=None)
            yield bl

    def test_add_youtube_video_returns_201(self):
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("YT Title", 300, None, False)),
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
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("twitch_clip", "AwesomeClip", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("Clip Title", 60, None, False)),
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
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("bilibili", "BV1test", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(
                    return_value=VideoMetadata(
                        "BV Title", 200, None, True, metadata_best_effort=True
                    )
                ),
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

    def test_bilibili_missing_duration_allowed_despite_length_cap(self):
        # Bilibili's 412 endpoint returns no duration; the dashboard length cap
        # must skip rather than 422 every Bilibili add on a capped channel.
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("bilibili", "BV1FjxHzGEkQ", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(
                    return_value=VideoMetadata(
                        "BV Title", None, None, False, metadata_best_effort=True
                    )
                ),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
            patch("routers.video_queue_router.ChannelRepository") as cr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            vqr.return_value.add = AsyncMock()
            vqr.return_value.get_current = AsyncMock(return_value=None)
            vqr.return_value.get_queued = AsyncMock(return_value=[])
            sr.return_value.get_or_create = AsyncMock(
                return_value=_make_settings(max_duration_seconds=600)
            )
            cr.return_value.get_broadcaster_display_name = AsyncMock(return_value=None)
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://bilibili.com/video/BV1FjxHzGEkQ"},
            )
        assert r.status_code == 201

    def test_unverifiable_duration_from_authoritative_source_returns_422(self):
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("YT", None, None, False)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            sr.return_value.get_or_create = AsyncMock(
                return_value=_make_settings(max_duration_seconds=600)
            )
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VIDEO_QUEUE.METADATA_UNVERIFIABLE"

    def test_add_twitch_vod_passes_start_seconds(self):
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(
                    return_value=ResolvedVideo("twitch_vod", "v999", False, start_seconds=90)
                ),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("VOD", 600, 10, False)),
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
            cr.return_value.get_broadcaster_display_name = AsyncMock(return_value="S")
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://www.twitch.tv/videos/v999?t=1m30s"},
            )
        assert r.status_code == 201
        assert vqr.return_value.add.await_args.kwargs["start_seconds"] == 90

    def test_invalid_url_returns_422(self):
        with patch(
            "routers.video_queue_router.resolve_video_url",
            AsyncMock(return_value=None),
        ):
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://example.com/not-a-video"},
            )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VIDEO_QUEUE.INVALID_URL"

    def test_unplayable_video_returns_422(self):
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(
                    return_value=VideoMetadata(
                        "Restricted",
                        300,
                        None,
                        False,
                        playable=False,
                        unplayable_reason="age_restricted",
                    )
                ),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VIDEO_QUEUE.NOT_PLAYABLE"

    def test_over_max_duration_seconds_returns_422(self):
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("Long", 1200, None, False)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            sr.return_value.get_or_create = AsyncMock(
                return_value=_make_settings(max_duration_seconds=600)
            )
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VIDEO_QUEUE.TOO_LONG"

    def test_blocked_video_returns_422(self, _stub_blocklist):
        _stub_blocklist.return_value.check = AsyncMock(
            return_value=_blocklist_entry(kind="keyword", value="lofi")
        )
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("chill lofi", 300, None, False)),
            ),
            patch("routers.video_queue_router.VideoQueueRepository") as vqr,
            patch("routers.video_queue_router.VideoQueueSettingsRepository") as sr,
        ):
            vqr.return_value.video_is_active = AsyncMock(return_value=False)
            sr.return_value.get_or_create = AsyncMock(return_value=_make_settings())
            r = _make_auth_client().post(
                "/api/video-queue/entries",
                json={"url": "https://youtube.com/watch?v=vid123"},
            )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VIDEO_QUEUE.BLOCKED"

    def test_queue_disabled_returns_403(self):
        with (
            patch(
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
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
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
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
                "routers.video_queue_router.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "routers.video_queue_router.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("Title", 300, None, False)),
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
