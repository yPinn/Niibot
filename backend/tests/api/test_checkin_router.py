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
from routers.checkin_router import get_checkin_collection_service
from routers.checkin_router import router as _checkin_router
from services.checkin_collection_service import (
    CheckinCollectionCard,
    CheckinCollectionSet,
    CheckinCollectionSnapshot,
)
from services.tenant_service import TenantContext
from shared.models.attendance import CheckinLeaderboardEntry, CheckinSettings

CHANNEL_ID = "channel-123"
_ACTION_HEADERS = {"X-Niibot-Action": "checkin-settings"}
_COLLECTION_ACTION_HEADERS = {"X-Niibot-Action": "checkin-collections"}
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


def _collection_service() -> MagicMock:
    service = MagicMock()
    snapshot = CheckinCollectionSnapshot(
        selected_set_key=None,
        total_cards=1,
        sets=(
            CheckinCollectionSet(
                key="aespa",
                name="aespa",
                card_count=1,
                cards=(
                    CheckinCollectionCard(
                        key="karina-01",
                        number=1,
                        name="Karina",
                        portrait_url="/images/collections/aespa/karina-01-r1.webp",
                        rarity_key="common",
                        rarity_name="普通",
                    ),
                ),
            ),
        ),
    )
    service.get_snapshot = AsyncMock(return_value=snapshot)
    service.select_set = AsyncMock(return_value=snapshot)
    return service


def _make_client(
    service: MagicMock,
    collection_service: MagicMock | None = None,
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_checkin_router)
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID,
        user_id="user-1",
        role="owner",
    )
    app.dependency_overrides[get_attendance_service] = lambda: service
    if collection_service is not None:
        app.dependency_overrides[get_checkin_collection_service] = lambda: collection_service
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
        reply_delay_seconds=None,
    )


def test_patch_settings_forwards_the_configured_reply_delay() -> None:
    service = _service()

    response = _make_client(service).patch(
        "/api/checkin/settings",
        json={"reply_delay_seconds": 5},
        headers=_ACTION_HEADERS,
    )

    assert response.status_code == 200
    service.update_settings.assert_awaited_once_with(
        CHANNEL_ID,
        timezone=None,
        success_template=None,
        duplicate_template=None,
        reply_delay_seconds=5,
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


def test_patch_rejects_reply_delay_above_the_cap() -> None:
    service = _service()

    response = _make_client(service).patch(
        "/api/checkin/settings",
        json={"reply_delay_seconds": 31},
        headers=_ACTION_HEADERS,
    )

    assert response.status_code == 422
    service.update_settings.assert_not_awaited()


def test_patch_rejects_negative_reply_delay() -> None:
    service = _service()

    response = _make_client(service).patch(
        "/api/checkin/settings",
        json={"reply_delay_seconds": -1},
        headers=_ACTION_HEADERS,
    )

    assert response.status_code == 422
    service.update_settings.assert_not_awaited()


def test_get_collections_returns_image_catalog_for_authenticated_tenant() -> None:
    collection_service = _collection_service()

    response = _make_client(_service(), collection_service).get("/api/checkin/collections")

    assert response.status_code == 200
    assert response.json() == {
        "selected_set_key": None,
        "total_cards": 1,
        "sets": [
            {
                "key": "aespa",
                "name": "aespa",
                "card_count": 1,
                "cards": [
                    {
                        "key": "karina-01",
                        "number": 1,
                        "name": "Karina",
                        "portrait_url": "/images/collections/aespa/karina-01-r1.webp",
                        "rarity_key": "common",
                        "rarity_name": "普通",
                    }
                ],
            }
        ],
    }
    collection_service.get_snapshot.assert_awaited_once_with(CHANNEL_ID)


def test_patch_collections_selects_one_set_for_authenticated_tenant() -> None:
    collection_service = _collection_service()

    response = _make_client(_service(), collection_service).patch(
        "/api/checkin/collections",
        json={"set_key": "aespa"},
        headers=_COLLECTION_ACTION_HEADERS,
    )

    assert response.status_code == 200
    collection_service.select_set.assert_awaited_once_with(CHANNEL_ID, "aespa")


def test_patch_collections_accepts_null_as_all_sets() -> None:
    collection_service = _collection_service()

    response = _make_client(_service(), collection_service).patch(
        "/api/checkin/collections",
        json={"set_key": None},
        headers=_COLLECTION_ACTION_HEADERS,
    )

    assert response.status_code == 200
    collection_service.select_set.assert_awaited_once_with(CHANNEL_ID, None)


def test_patch_collections_rejects_tenant_id_and_missing_action_header() -> None:
    collection_service = _collection_service()
    client = _make_client(_service(), collection_service)

    extra = client.patch(
        "/api/checkin/collections",
        json={"channel_id": "other", "set_key": "aespa"},
        headers=_COLLECTION_ACTION_HEADERS,
    )
    missing_header = client.patch(
        "/api/checkin/collections",
        json={"set_key": "aespa"},
    )

    assert extra.status_code == 422
    assert missing_header.status_code == 422
    collection_service.select_set.assert_not_awaited()


def test_patch_collections_maps_unknown_set_without_leaking_internal_value() -> None:
    collection_service = _collection_service()
    collection_service.select_set = AsyncMock(side_effect=ValueError("secret-set"))

    response = _make_client(_service(), collection_service).patch(
        "/api/checkin/collections",
        json={"set_key": "unknown"},
        headers=_COLLECTION_ACTION_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHECKIN_COLLECTION.INVALID_SET"
    assert "secret-set" not in response.text
