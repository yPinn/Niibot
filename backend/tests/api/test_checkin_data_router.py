"""Owner-only HTTP contract for check-in export and data clearing."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-checkin-data-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import require_self_tenant_owner
from core.error_handlers import register_exception_handlers
from routers.checkin_router import get_checkin_data_service, router
from services.checkin_data_service import (
    CheckinClearScope,
    CheckinDataSummary,
)
from services.tenant_service import TenantContext

_TENANT = TenantContext(
    channel_id="channel-router",
    user_id="00000000-0000-0000-0000-000000000001",
    role="owner",
    channel_name="owner_login",
)
_SUMMARY = CheckinDataSummary(
    participant_count=2,
    total_days=19,
    imported_viewers=1,
    imported_days=15,
    ledger_checkins=4,
    card_draws=4,
    checkin_events=4,
)


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _client(service: MagicMock) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_self_tenant_owner] = lambda: _TENANT
    app.dependency_overrides[get_checkin_data_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_summary_exposes_two_clear_impacts_and_confirmation_text() -> None:
    service = MagicMock()
    service.get_summary = AsyncMock(return_value=_SUMMARY)

    response = _client(service).get("/api/checkin/data/summary")

    assert response.status_code == 200
    assert response.json() == {
        "participant_count": 2,
        "total_days": 19,
        "imported_viewers": 1,
        "imported_days": 15,
        "ledger_checkins": 4,
        "card_draws": 4,
        "checkin_events": 4,
        "confirmation_text": "owner_login",
    }
    service.get_summary.assert_awaited_once_with(_TENANT.channel_id)


def test_export_download_is_private_utf8_csv() -> None:
    service = MagicMock()
    service.export_csv = AsyncMock(return_value=b"\xef\xbb\xbfUsername\r\nalice\r\n")

    response = _client(service).get("/api/checkin/data/export")

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "private, no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert "owner_login" in response.headers["content-disposition"]


def test_clear_requires_exact_channel_confirmation_and_mutation_header() -> None:
    service = MagicMock()
    service.clear = AsyncMock(return_value=_SUMMARY)
    client = _client(service)

    wrong_confirmation = client.post(
        "/api/checkin/data/clear",
        headers={"X-Niibot-Action": "checkin-data"},
        json={"scope": "imported", "confirmation": "someone_else"},
    )
    missing_header = client.post(
        "/api/checkin/data/clear",
        json={"scope": "imported", "confirmation": "owner_login"},
    )

    assert wrong_confirmation.status_code == 400
    assert wrong_confirmation.json()["error"]["code"] == "CHECKIN_DATA.CONFIRMATION_INVALID"
    assert missing_header.status_code == 422
    service.clear.assert_not_awaited()


def test_clear_accepts_only_closed_scopes_and_returns_exact_impact() -> None:
    service = MagicMock()
    service.clear = AsyncMock(return_value=_SUMMARY.with_scope(CheckinClearScope.IMPORTED))
    client = _client(service)

    invalid = client.post(
        "/api/checkin/data/clear",
        headers={"X-Niibot-Action": "checkin-data"},
        json={"scope": "settings", "confirmation": "owner_login"},
    )
    response = client.post(
        "/api/checkin/data/clear",
        headers={"X-Niibot-Action": "checkin-data"},
        json={"scope": "imported", "confirmation": " owner_login "},
    )

    assert invalid.status_code == 422
    assert response.status_code == 200
    assert response.json()["scope"] == "imported"
    assert response.json()["imported_viewers"] == 1
    service.clear.assert_awaited_once_with(
        channel_id=_TENANT.channel_id,
        actor_user_id=_TENANT.user_id,
        scope=CheckinClearScope.IMPORTED,
    )
