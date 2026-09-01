"""Tests for tenant-scoped check-in settings routes."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-checkin-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import get_attendance_service, require_self_tenant_access
from core.error_handlers import register_exception_handlers
from routers.checkin_router import router as _checkin_router
from services.tenant_service import TenantContext
from shared.models.attendance import CheckinLeaderboardEntry, CheckinSettings

CHANNEL_ID = "channel-123"
_ACTION_HEADERS = {"X-Niibot-Action": "checkin-settings"}
_NOW = datetime(2026, 8, 31, tzinfo=UTC)
_SETTINGS = CheckinSettings(
    channel_id=CHANNEL_ID,
    timezone="Asia/Taipei",
    success_template="$(@user) 簽到成功，累積 $(count) 天！",
    duplicate_template="$(@user) 今天已經簽到過了，目前累積 $(count) 天！",
    created_at=_NOW,
    updated_at=_NOW,
)


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _service() -> MagicMock:
    service = MagicMock()
    service.get_settings = AsyncMock(return_value=_SETTINGS)
    service.update_settings = AsyncMock(return_value=_SETTINGS)
    service.get_leaderboard = AsyncMock(
        return_value=(
            CheckinLeaderboardEntry(
                rank=1,
                user_id="viewer-1",
                username="alice",
                display_name="Alice",
                total_days=12,
                last_checkin_date=date(2026, 8, 31),
            ),
        )
    )
    return service


def _make_client(service: MagicMock) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_checkin_router)
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID,
        user_id="user-1",
        role="owner",
    )
    app.dependency_overrides[get_attendance_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_get_settings_uses_authenticated_tenant() -> None:
    service = _service()

    response = _make_client(service).get("/api/checkin/settings")

    assert response.status_code == 200
    assert response.json()["channel_id"] == CHANNEL_ID
    assert response.json()["timezone"] == "Asia/Taipei"
    service.get_settings.assert_awaited_once_with(CHANNEL_ID)


def test_get_leaderboard_uses_authenticated_tenant() -> None:
    service = _service()

    response = _make_client(service).get("/api/checkin/leaderboard")

    assert response.status_code == 200
    assert response.json() == [
        {
            "rank": 1,
            "user_id": "viewer-1",
            "username": "alice",
            "display_name": "Alice",
            "total_days": 12,
            "last_checkin_date": "2026-08-31",
        }
    ]
    service.get_leaderboard.assert_awaited_once_with(CHANNEL_ID)


def test_patch_settings_uses_authenticated_tenant_and_action_header() -> None:
    service = _service()
    body = {
        "timezone": "Asia/Tokyo",
        "success_template": "$(@user) 第 $(count) 天",
        "duplicate_template": "$(@user) 今天已簽到",
    }

    response = _make_client(service).patch(
        "/api/checkin/settings", json=body, headers=_ACTION_HEADERS
    )

    assert response.status_code == 200
    service.update_settings.assert_awaited_once_with(
        CHANNEL_ID,
        timezone="Asia/Tokyo",
        success_template="$(@user) 第 $(count) 天",
        duplicate_template="$(@user) 今天已簽到",
    )


def test_patch_rejects_tenant_id_in_request_body() -> None:
    service = _service()

    response = _make_client(service).patch(
        "/api/checkin/settings",
        json={"channel_id": "other-channel", "timezone": "Asia/Tokyo"},
        headers=_ACTION_HEADERS,
    )

    assert response.status_code == 422
    service.update_settings.assert_not_awaited()


def test_patch_requires_explicit_mutation_header() -> None:
    service = _service()

    response = _make_client(service).patch("/api/checkin/settings", json={"timezone": "Asia/Tokyo"})

    assert response.status_code == 422
    service.update_settings.assert_not_awaited()


def test_patch_rejects_empty_update() -> None:
    service = _service()

    response = _make_client(service).patch(
        "/api/checkin/settings", json={}, headers=_ACTION_HEADERS
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHECKIN_SETTINGS.INVALID"
    service.update_settings.assert_not_awaited()


def test_patch_maps_domain_validation_without_leaking_internal_error() -> None:
    service = _service()
    service.update_settings = AsyncMock(side_effect=ValueError("Not/AZone"))

    response = _make_client(service).patch(
        "/api/checkin/settings",
        json={"timezone": "Not/AZone"},
        headers=_ACTION_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHECKIN_SETTINGS.INVALID"
    assert "Not/AZone" not in response.text


def test_patch_rejects_oversized_template_before_service() -> None:
    service = _service()

    response = _make_client(service).patch(
        "/api/checkin/settings",
        json={"success_template": "x" * 501},
        headers=_ACTION_HEADERS,
    )

    assert response.status_code == 422
    service.update_settings.assert_not_awaited()
