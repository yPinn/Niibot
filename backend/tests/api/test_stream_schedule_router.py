"""Tests for tenant-scoped stream schedule routes."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-stream-schedule-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.dependencies import (
    get_stream_schedule_service,
    get_twitch_api,
    require_self_tenant_access,
)
from core.error_handlers import register_exception_handlers
from routers.stream_schedule_router import StreamScheduleCreate
from routers.stream_schedule_router import router as _stream_schedule_router
from services.tenant_service import TenantContext
from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleSegment,
    StreamScheduleSettings,
)

CHANNEL_ID = "channel-123"
_SETTINGS_HEADERS = {"X-Niibot-Action": "stream-schedule-settings"}
_CREATE_HEADERS = {"X-Niibot-Action": "stream-schedule-create"}
_UPDATE_HEADERS = {"X-Niibot-Action": "stream-schedule-update"}
_DELETE_HEADERS = {"X-Niibot-Action": "stream-schedule-delete"}
_SEG_CREATE_HEADERS = {"X-Niibot-Action": "stream-schedule-segment-create"}
_SEG_UPDATE_HEADERS = {"X-Niibot-Action": "stream-schedule-segment-update"}
_SEG_DELETE_HEADERS = {"X-Niibot-Action": "stream-schedule-segment-delete"}
_NOW = datetime(2026, 9, 21, tzinfo=UTC)

_SETTINGS = StreamScheduleSettings(
    channel_id=CHANNEL_ID, timezone="Asia/Taipei", enabled=True, created_at=_NOW, updated_at=_NOW
)
_SCHEDULE = StreamSchedule(
    id=1,
    channel_id=CHANNEL_ID,
    kind=ScheduleKind.RECURRING,
    weekday=0,
    specific_date=None,
    start_time=time(20, 0),
    duration_minutes=180,
    title_template="週一開台",
    created_at=_NOW,
    updated_at=_NOW,
)
_SEGMENT = StreamScheduleSegment(
    id=1, channel_id=CHANNEL_ID, schedule_id=1, offset_minutes=0, title_template="聊天"
)


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _service() -> MagicMock:
    service = MagicMock()
    service.get_settings = AsyncMock(return_value=_SETTINGS)
    service.update_settings = AsyncMock(return_value=_SETTINGS)
    service.list_schedules = AsyncMock(return_value=[_SCHEDULE])
    service.create_schedule = AsyncMock(return_value=_SCHEDULE)
    service.update_schedule = AsyncMock(return_value=_SCHEDULE)
    service.delete_schedule = AsyncMock(return_value=True)
    service.list_segments = AsyncMock(return_value=[_SEGMENT])
    service.add_segment = AsyncMock(return_value=_SEGMENT)
    service.update_segment = AsyncMock(return_value=_SEGMENT)
    service.delete_segment = AsyncMock(return_value=True)
    return service


def _twitch_api(search_results: list[dict] | None = None) -> MagicMock:
    api = MagicMock()
    api.search_categories = AsyncMock(return_value=search_results or [])
    return api


def _make_client(service: MagicMock, twitch_api: MagicMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_stream_schedule_router)
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID, user_id="user-1", role="owner"
    )
    app.dependency_overrides[get_stream_schedule_service] = lambda: service
    app.dependency_overrides[get_twitch_api] = lambda: twitch_api or _twitch_api()
    return TestClient(app, raise_server_exceptions=False)


class TestSettings:
    def test_get_settings(self) -> None:
        service = _service()
        response = _make_client(service).get("/api/stream-schedule/settings")
        assert response.status_code == 200
        assert response.json()["timezone"] == "Asia/Taipei"
        service.get_settings.assert_awaited_once_with(CHANNEL_ID)

    def test_update_settings_requires_action_header(self) -> None:
        service = _service()
        response = _make_client(service).patch(
            "/api/stream-schedule/settings", json={"timezone": "Asia/Tokyo"}
        )
        assert response.status_code == 422
        service.update_settings.assert_not_awaited()

    def test_update_settings(self) -> None:
        service = _service()
        response = _make_client(service).patch(
            "/api/stream-schedule/settings",
            json={"timezone": "Asia/Tokyo"},
            headers=_SETTINGS_HEADERS,
        )
        assert response.status_code == 200
        service.update_settings.assert_awaited_once_with(
            CHANNEL_ID, timezone="Asia/Tokyo", enabled=None
        )

    def test_update_settings_invalid_value_maps_to_400(self) -> None:
        service = _service()
        service.update_settings = AsyncMock(side_effect=ValueError("invalid timezone"))
        response = _make_client(service).patch(
            "/api/stream-schedule/settings",
            json={"timezone": "Not/AZone"},
            headers=_SETTINGS_HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "STREAM_SCHEDULE.INVALID"


class TestSchedules:
    def test_list_schedules(self) -> None:
        service = _service()
        response = _make_client(service).get("/api/stream-schedule/schedules")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["kind"] == "recurring"
        assert body[0]["weekday"] == 0

    def test_create_recurring_schedule(self) -> None:
        service = _service()
        response = _make_client(service).post(
            "/api/stream-schedule/schedules",
            json={
                "kind": "recurring",
                "weekday": 0,
                "start_time": "20:00:00",
                "duration_minutes": 180,
                "title_template": "週一開台",
            },
            headers=_CREATE_HEADERS,
        )
        assert response.status_code == 201
        service.create_schedule.assert_awaited_once()

    def test_create_schedule_rejects_recurring_with_specific_date(self) -> None:
        service = _service()
        response = _make_client(service).post(
            "/api/stream-schedule/schedules",
            json={
                "kind": "recurring",
                "weekday": 0,
                "specific_date": "2026-09-21",
                "start_time": "20:00:00",
                "duration_minutes": 180,
            },
            headers=_CREATE_HEADERS,
        )
        assert response.status_code == 422
        service.create_schedule.assert_not_awaited()

    def test_update_schedule_not_found(self) -> None:
        service = _service()
        service.update_schedule = AsyncMock(return_value=None)
        response = _make_client(service).put(
            "/api/stream-schedule/schedules/999",
            json={"enabled": False},
            headers=_UPDATE_HEADERS,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "STREAM_SCHEDULE.NOT_FOUND"

    def test_delete_schedule(self) -> None:
        service = _service()
        response = _make_client(service).delete(
            "/api/stream-schedule/schedules/1", headers=_DELETE_HEADERS
        )
        assert response.status_code == 204
        service.delete_schedule.assert_awaited_once_with(CHANNEL_ID, 1)

    def test_delete_schedule_not_found(self) -> None:
        service = _service()
        service.delete_schedule = AsyncMock(return_value=False)
        response = _make_client(service).delete(
            "/api/stream-schedule/schedules/999", headers=_DELETE_HEADERS
        )
        assert response.status_code == 404


class TestSegments:
    def test_list_segments(self) -> None:
        service = _service()
        response = _make_client(service).get("/api/stream-schedule/schedules/1/segments")
        assert response.status_code == 200
        assert len(response.json()) == 1
        service.list_segments.assert_awaited_once_with(CHANNEL_ID, 1)

    def test_create_segment(self) -> None:
        service = _service()
        response = _make_client(service).post(
            "/api/stream-schedule/schedules/1/segments",
            json={"offset_minutes": 0, "title_template": "聊天"},
            headers=_SEG_CREATE_HEADERS,
        )
        assert response.status_code == 201
        service.add_segment.assert_awaited_once()

    def test_create_segment_for_missing_schedule_returns_404(self) -> None:
        """Cross-tenant / non-existent schedule_id — the service returns None,
        which must surface as 404, not a silent 200 with a different owner's row."""
        service = _service()
        service.add_segment = AsyncMock(return_value=None)
        response = _make_client(service).post(
            "/api/stream-schedule/schedules/999/segments",
            json={"offset_minutes": 0, "title_template": "聊天"},
            headers=_SEG_CREATE_HEADERS,
        )
        assert response.status_code == 404

    def test_update_segment_not_found(self) -> None:
        service = _service()
        service.update_segment = AsyncMock(return_value=None)
        response = _make_client(service).put(
            "/api/stream-schedule/segments/999",
            json={"title_template": "x"},
            headers=_SEG_UPDATE_HEADERS,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "STREAM_SCHEDULE_SEGMENT.NOT_FOUND"

    def test_create_segment_with_preresolved_game(self) -> None:
        """The frontend's picker already resolved id+name via /games/search —
        the router trusts the pair as-is, no server-side re-resolution."""
        service = _service()
        response = _make_client(service).post(
            "/api/stream-schedule/schedules/1/segments",
            json={
                "offset_minutes": 0,
                "title_template": "聊天",
                "game_id": "509658",
                "game_name": "Just Chatting",
            },
            headers=_SEG_CREATE_HEADERS,
        )
        assert response.status_code == 201
        service.add_segment.assert_awaited_once_with(
            CHANNEL_ID,
            1,
            offset_minutes=0,
            title_template="聊天",
            game_id="509658",
            game_name="Just Chatting",
            sort_order=0,
        )

    def test_create_segment_game_id_without_name_rejected(self) -> None:
        service = _service()
        response = _make_client(service).post(
            "/api/stream-schedule/schedules/1/segments",
            json={"offset_minutes": 0, "game_id": "509658"},
            headers=_SEG_CREATE_HEADERS,
        )
        assert response.status_code == 422
        service.add_segment.assert_not_awaited()

    def test_update_segment_cleared_game_id_clears_game(self) -> None:
        service = _service()
        response = _make_client(service).put(
            "/api/stream-schedule/segments/1",
            json={"game_id": "", "game_name": ""},
            headers=_SEG_UPDATE_HEADERS,
        )
        assert response.status_code == 200
        service.update_segment.assert_awaited_once_with(
            CHANNEL_ID,
            1,
            offset_minutes=None,
            title_template=None,
            game_id=None,
            game_name=None,
            sort_order=None,
            clear_game=True,
        )

    def test_update_segment_mismatched_game_pair_rejected(self) -> None:
        service = _service()
        response = _make_client(service).put(
            "/api/stream-schedule/segments/1",
            json={"game_id": "509658", "game_name": ""},
            headers=_SEG_UPDATE_HEADERS,
        )
        assert response.status_code == 422
        service.update_segment.assert_not_awaited()

    def test_update_segment_omitted_game_name_leaves_it_untouched(self) -> None:
        service = _service()
        response = _make_client(service).put(
            "/api/stream-schedule/segments/1",
            json={"title_template": "換個標題"},
            headers=_SEG_UPDATE_HEADERS,
        )
        assert response.status_code == 200
        service.update_segment.assert_awaited_once_with(
            CHANNEL_ID,
            1,
            offset_minutes=None,
            title_template="換個標題",
            game_id=None,
            game_name=None,
            sort_order=None,
            clear_game=False,
        )

    def test_delete_segment(self) -> None:
        service = _service()
        response = _make_client(service).delete(
            "/api/stream-schedule/segments/1", headers=_SEG_DELETE_HEADERS
        )
        assert response.status_code == 204
        service.delete_segment.assert_awaited_once_with(CHANNEL_ID, 1)


class TestScheduleCreateValidation:
    """Direct pydantic-model tests for the kind/weekday/specific_date consistency rule."""

    def test_recurring_without_weekday_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamScheduleCreate(
                kind=ScheduleKind.RECURRING, start_time=time(20, 0), duration_minutes=60
            )

    def test_one_off_without_specific_date_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamScheduleCreate(
                kind=ScheduleKind.ONE_OFF, start_time=time(20, 0), duration_minutes=60
            )

    def test_one_off_with_weekday_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamScheduleCreate(
                kind=ScheduleKind.ONE_OFF,
                weekday=0,
                specific_date=date(2026, 9, 21),
                start_time=time(20, 0),
                duration_minutes=60,
            )

    def test_valid_one_off_accepted(self) -> None:
        model = StreamScheduleCreate(
            kind=ScheduleKind.ONE_OFF,
            specific_date=date(2026, 9, 21),
            start_time=time(20, 0),
            duration_minutes=60,
        )
        assert model.specific_date == date(2026, 9, 21)


class TestGameSearch:
    def test_search_returns_matches(self) -> None:
        service = _service()
        twitch_api = _twitch_api(
            search_results=[
                {
                    "id": "509658",
                    "name": "Just Chatting",
                    "box_art_url": "https://x/{width}x{height}.jpg",
                }
            ]
        )
        response = _make_client(service, twitch_api).get(
            "/api/stream-schedule/games/search", params={"q": "just chat"}
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": "509658",
                "name": "Just Chatting",
                "box_art_url": "https://x/{width}x{height}.jpg",
            }
        ]
        twitch_api.search_categories.assert_awaited_once_with("just chat")

    def test_search_requires_nonempty_query(self) -> None:
        service = _service()
        response = _make_client(service).get("/api/stream-schedule/games/search", params={"q": ""})
        assert response.status_code == 422
