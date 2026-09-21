"""Owner-only HTTP contract for check-in summary preview and apply."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-checkin-import-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import require_self_tenant_owner
from core.error_handlers import register_exception_handlers
from routers.checkin_router import get_checkin_import_service, router
from services.checkin_import.models import (
    CheckinImportPreview,
    CheckinImportResult,
    IdentityResolution,
    ImportPreviewRow,
    ImportRowStatus,
)
from services.checkin_import.service import stash_preview
from services.tenant_service import TenantContext

_TENANT = TenantContext(
    channel_id="channel-router",
    user_id="00000000-0000-0000-0000-000000000001",
    role="owner",
)


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _preview() -> CheckinImportPreview:
    return CheckinImportPreview(
        source="chiwabots",
        source_format="csv",
        source_timezone="Asia/Taipei",
        through_date=date(2026, 9, 10),
        content_sha256="a" * 64,
        column_mapping=(("last_checkin_date", 2), ("total_days", 1), ("username", 0)),
        sheet_name=None,
        rows=(
            ImportPreviewRow(
                key="row-ready",
                source_row=2,
                user_id="101",
                username="alice",
                display_name="Alice",
                total_days=15,
                last_checkin_date=date(2026, 9, 10),
                current_streak=3,
                daily_order=5,
                status=ImportRowStatus.READY,
            ),
        ),
    )


def _client(service: MagicMock) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_self_tenant_owner] = lambda: _TENANT
    app.dependency_overrides[get_checkin_import_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_preview_accepts_csv_upload_and_returns_default_ready_selection() -> None:
    service = MagicMock()
    service.preview = AsyncMock(return_value=_preview())

    response = _client(service).post(
        "/api/checkin/import/summary/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        data={
            "source": "chiwabots",
            "source_timezone": "Asia/Taipei",
            "through_date": "2026-09-10",
        },
        files={
            "upload": (
                "checkins.csv",
                b"Username,Count,LastDate\nalice,15,2026-09-10\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_format"] == "csv"
    assert body["default_selection"] == {"row-ready": True}
    assert body["rows"][0]["total_days"] == 15
    kwargs = service.preview.await_args.kwargs
    assert kwargs["channel_id"] == _TENANT.channel_id
    assert kwargs["parsed"].rows[0].username == "alice"


def test_columns_inspection_returns_headers_and_suggested_mapping() -> None:
    service = MagicMock()

    response = _client(service).post(
        "/api/checkin/import/summary/columns",
        headers={"X-Niibot-Action": "checkin-import"},
        files={
            "upload": (
                "checkins.csv",
                "觀眾名稱,COUNT,簽到日期\nalice,15,2026-09-10\n".encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "source_format": "csv",
        "sheet_name": None,
        "headers": ["觀眾名稱", "COUNT", "簽到日期"],
        "suggested_mapping": {"total_days": 1},
    }


def test_preview_accepts_manual_column_index_mapping() -> None:
    service = MagicMock()
    service.preview = AsyncMock(return_value=_preview())

    response = _client(service).post(
        "/api/checkin/import/summary/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        data={
            "source": "other-bot",
            "source_timezone": "Asia/Taipei",
            "through_date": "2026-09-10",
            "column_mapping": (
                '{"username":0,"total_days":1,"last_checkin_date":2,"current_streak":3}'
            ),
        },
        files={
            "upload": (
                "checkins.csv",
                "觀眾,累積,末次,連續\nalice,15,2026-09-10,3\n".encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    row = service.preview.await_args.kwargs["parsed"].rows[0]
    assert row.username == "alice"
    assert row.total_days == 15
    assert row.current_streak == 3


def test_preview_requires_mutation_header_and_exactly_one_input() -> None:
    service = MagicMock()
    service.preview = AsyncMock(return_value=_preview())
    client = _client(service)

    missing_header = client.post(
        "/api/checkin/import/summary/preview",
        data={
            "source": "chiwabots",
            "source_timezone": "Asia/Taipei",
            "through_date": "2026-09-10",
        },
        files={"upload": ("checkins.csv", b"x", "text/csv")},
    )
    missing_input = client.post(
        "/api/checkin/import/summary/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        data={
            "source": "chiwabots",
            "source_timezone": "Asia/Taipei",
            "through_date": "2026-09-10",
        },
    )

    assert missing_header.status_code == 422
    assert missing_input.status_code == 400
    assert missing_input.json()["error"]["code"] == "CHECKIN_IMPORT.INVALID"


def test_apply_uses_tenant_bound_preview_and_confirmation() -> None:
    preview = _preview()
    import_id = stash_preview(_TENANT.user_id, _TENANT.channel_id, preview)
    service = MagicMock()
    service.apply = AsyncMock(return_value=CheckinImportResult(batch_id="batch-1", imported_rows=1))

    response = _client(service).post(
        "/api/checkin/import/apply",
        headers={"X-Niibot-Action": "checkin-import"},
        json={
            "import_id": import_id,
            "selected_keys": ["row-ready"],
            "old_source_disabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "batch_id": "batch-1",
        "imported_rows": 1,
        "already_applied": False,
    }
    service.apply.assert_awaited_once_with(
        channel_id=_TENANT.channel_id,
        actor_user_id=_TENANT.user_id,
        preview=preview,
        selected_keys=["row-ready"],
        old_source_disabled=True,
    )


def test_identity_preview_remaps_only_tenant_bound_unresolved_rows() -> None:
    unresolved = CheckinImportPreview(
        source="other-bot",
        source_format="csv",
        source_timezone="Asia/Taipei",
        through_date=date(2026, 9, 10),
        content_sha256="b" * 64,
        column_mapping=(("last_checkin_date", 2), ("total_days", 1), ("username", 0)),
        sheet_name=None,
        rows=(
            ImportPreviewRow(
                key="row-aaaaaaaaaaaaaaaaaaaaaaaa",
                source_row=2,
                user_id=None,
                username=None,
                display_name=None,
                total_days=15,
                last_checkin_date=date(2026, 9, 10),
                current_streak=3,
                daily_order=None,
                status=ImportRowStatus.UNRESOLVED,
                source_username="alice_old",
            ),
        ),
    )
    remapped = CheckinImportPreview(
        source=unresolved.source,
        source_format=unresolved.source_format,
        source_timezone=unresolved.source_timezone,
        through_date=unresolved.through_date,
        content_sha256=unresolved.content_sha256,
        column_mapping=unresolved.column_mapping,
        sheet_name=None,
        rows=(
            ImportPreviewRow(
                key=unresolved.rows[0].key,
                source_row=2,
                user_id="101",
                username="alice_new",
                display_name="Alice New",
                total_days=15,
                last_checkin_date=date(2026, 9, 10),
                current_streak=3,
                daily_order=None,
                status=ImportRowStatus.REVIEW,
                source_username="alice_old",
                identity_resolution=IdentityResolution.MANUAL,
            ),
        ),
    )
    import_id = stash_preview(_TENANT.user_id, _TENANT.channel_id, unresolved)
    service = MagicMock()
    service.remap_identities = AsyncMock(return_value=remapped)

    response = _client(service).post(
        "/api/checkin/import/identity/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        json={
            "import_id": import_id,
            "mappings": [
                {
                    "row_key": unresolved.rows[0].key,
                    "target_type": "username",
                    "value": "alice_new",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["import_id"] != import_id
    assert body["rows"][0]["status"] == "review"
    assert body["default_selection"] == {unresolved.rows[0].key: False}
    service.remap_identities.assert_awaited_once()


def test_identity_preview_rejects_invalid_target_and_cross_tenant_preview() -> None:
    service = MagicMock()
    service.remap_identities = AsyncMock()
    client = _client(service)
    cross_tenant_id = stash_preview(_TENANT.user_id, "other-channel", _preview())

    invalid_target = client.post(
        "/api/checkin/import/identity/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        json={
            "import_id": "preview-missing",
            "mappings": [
                {
                    "row_key": "row-aaaaaaaaaaaaaaaaaaaaaaaa",
                    "target_type": "user_id",
                    "value": "not-id",
                }
            ],
        },
    )
    invalid_target_type = client.post(
        "/api/checkin/import/identity/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        json={
            "import_id": "preview-missing",
            "mappings": [
                {
                    "row_key": "row-aaaaaaaaaaaaaaaaaaaaaaaa",
                    "target_type": "display_name",
                    "value": "Alice",
                }
            ],
        },
    )
    cross_tenant = client.post(
        "/api/checkin/import/identity/preview",
        headers={"X-Niibot-Action": "checkin-import"},
        json={
            "import_id": cross_tenant_id,
            "mappings": [
                {
                    "row_key": "row-aaaaaaaaaaaaaaaaaaaaaaaa",
                    "target_type": "username",
                    "value": "alice",
                }
            ],
        },
    )

    assert invalid_target.status_code == 422
    assert invalid_target_type.status_code == 422
    assert cross_tenant.status_code == 404
    service.remap_identities.assert_not_awaited()


def test_apply_rejects_preview_from_another_tenant() -> None:
    import_id = stash_preview(_TENANT.user_id, "other-channel", _preview())
    service = MagicMock()
    service.apply = AsyncMock()

    response = _client(service).post(
        "/api/checkin/import/apply",
        headers={"X-Niibot-Action": "checkin-import"},
        json={
            "import_id": import_id,
            "selected_keys": ["row-ready"],
            "old_source_disabled": True,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHECKIN_IMPORT.PREVIEW_EXPIRED"
    service.apply.assert_not_awaited()
