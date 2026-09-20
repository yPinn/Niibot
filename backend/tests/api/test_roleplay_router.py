"""Tenant-path API contracts for Canon Role-play authoring."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-roleplay-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("BOT_ID", "bot-test")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.dependencies import get_roleplay_service, require_tenant_access
from core.error_handlers import register_exception_handlers
from routers import roleplay_router
from services.roleplay_service import RoleplayImportOutcome
from services.tenant_service import TenantContext
from shared.models.roleplay import RoleplayRevision, RoleplaySet
from shared.roleplay import compile_roleplay_package, encode_roleplay_package
from shared.roleplay.portable import (
    MAX_PORTABLE_ROLEPLAY_BYTES,
    build_roleplay_character_export,
)
from tests.shared.roleplay.factories import sample_roleplay_package

_CHANNEL_ID = "channel-a"
_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_SET_ID = UUID("11111111-1111-4111-8111-111111111111")
_NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
_ACTION = {"X-Niibot-Action": "roleplay-settings"}


def _revision() -> RoleplayRevision:
    package = sample_roleplay_package()
    return RoleplayRevision(
        id=41,
        channel_id=_CHANNEL_ID,
        roleplay_set_id=_SET_ID,
        revision_number=1,
        package=package,
        compiled=compile_roleplay_package(package),
        published_at=_NOW,
    )


def _roleplay_set(*, archived: bool = False, published: bool = False) -> RoleplaySet:
    return RoleplaySet(
        id=_SET_ID,
        channel_id=_CHANNEL_ID,
        name="月港守望者",
        draft=sample_roleplay_package(),
        draft_version=1,
        published=_revision() if published else None,
        archived_at=_NOW if archived else None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _service() -> MagicMock:
    service = MagicMock()
    service.list_sets = AsyncMock(return_value=(_roleplay_set(),))
    service.get_set = AsyncMock(return_value=_roleplay_set())
    service.create_set = AsyncMock(return_value=_roleplay_set())
    service.update_draft = AsyncMock(return_value=_roleplay_set())
    service.publish = AsyncMock(return_value=_revision())
    service.activate = AsyncMock(return_value=_revision())
    service.archive = AsyncMock(return_value=_roleplay_set(archived=True))
    service.use_persona = AsyncMock(return_value=None)
    service.export_revision = AsyncMock(
        return_value=build_roleplay_character_export(
            display_name="月港守望者",
            package=sample_roleplay_package(),
            compiled=compile_roleplay_package(sample_roleplay_package()),
            exported_at=_NOW,
        )
    )
    service.import_character = AsyncMock(
        return_value=RoleplayImportOutcome(
            mode="copy",
            roleplay_set=_roleplay_set(),
            revision=None,
            reused=False,
        )
    )
    return service


def _client(service: MagicMock, *, role: str = "manager") -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(roleplay_router.router)
    app.dependency_overrides[get_roleplay_service] = lambda: service
    app.dependency_overrides[require_tenant_access] = lambda: TenantContext(
        channel_id=_CHANNEL_ID,
        user_id=_USER_ID,
        role=role,  # type: ignore[arg-type]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_manager_lists_only_the_path_tenant_sets() -> None:
    service = _service()

    response = _client(service).get(f"/api/tenants/{_CHANNEL_ID}/roleplay-sets")

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(_SET_ID)
    assert "draft" not in response.json()[0]
    service.list_sets.assert_awaited_once_with(_CHANNEL_ID, include_archived=False)


def test_list_can_explicitly_include_archived_sets() -> None:
    service = _service()

    response = _client(service).get(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets?include_archived=true"
    )

    assert response.status_code == 200
    service.list_sets.assert_awaited_once_with(_CHANNEL_ID, include_archived=True)


def test_create_forwards_strict_document_and_requires_action_header() -> None:
    service = _service()
    document = encode_roleplay_package(sample_roleplay_package())

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets",
        json={"name": "月港守望者", "draft": document},
        headers=_ACTION,
    )

    assert response.status_code == 201
    assert response.json()["draft"] == document
    service.create_set.assert_awaited_once_with(
        _CHANNEL_ID,
        name="月港守望者",
        draft=document,
    )


def test_create_rejects_tenant_id_in_body() -> None:
    service = _service()

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets",
        json={
            "channel_id": "channel-b",
            "name": "月港守望者",
            "draft": encode_roleplay_package(sample_roleplay_package()),
        },
        headers=_ACTION,
    )

    assert response.status_code == 422
    service.create_set.assert_not_awaited()


def test_mutation_requires_csrf_preflight_header() -> None:
    service = _service()

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets",
        json={
            "name": "月港守望者",
            "draft": encode_roleplay_package(sample_roleplay_package()),
        },
    )

    assert response.status_code == 422
    service.create_set.assert_not_awaited()


def test_read_returns_authoring_document_for_exact_path_tenant() -> None:
    service = _service()

    response = _client(service).get(f"/api/tenants/{_CHANNEL_ID}/roleplay-sets/{_SET_ID}")

    assert response.status_code == 200
    assert response.json()["name"] == "月港守望者"
    assert response.json()["draft_version"] == 1
    service.get_set.assert_awaited_once_with(_CHANNEL_ID, _SET_ID)


def test_update_forwards_optimistic_version_and_optional_name() -> None:
    service = _service()
    document = encode_roleplay_package(sample_roleplay_package())

    response = _client(service).patch(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets/{_SET_ID}",
        json={"name": "新名稱", "draft": document, "expected_draft_version": 1},
        headers=_ACTION,
    )

    assert response.status_code == 200
    service.update_draft.assert_awaited_once_with(
        _CHANNEL_ID,
        _SET_ID,
        name="新名稱",
        draft=document,
        expected_draft_version=1,
    )


def test_publish_returns_compiled_preview_without_changing_mode() -> None:
    service = _service()

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets/{_SET_ID}/revisions",
        json={"expected_draft_version": 1},
        headers=_ACTION,
    )

    assert response.status_code == 201
    assert response.json()["id"] == 41
    assert response.json()["compact_capsule"]
    assert response.json()["package"] == encode_roleplay_package(sample_roleplay_package())
    service.publish.assert_awaited_once_with(_CHANNEL_ID, _SET_ID, expected_draft_version=1)


def test_activate_returns_explicit_roleplay_mode() -> None:
    service = _service()

    response = _client(service).put(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets/{_SET_ID}/active-revision",
        json={"revision_id": 41},
        headers=_ACTION,
    )

    assert response.status_code == 200
    assert response.json()["assistant_mode"] == "roleplay"
    assert response.json()["active_roleplay_revision_id"] == 41
    service.activate.assert_awaited_once_with(_CHANNEL_ID, _SET_ID, revision_id=41)


def test_delete_active_roleplay_switches_to_persona_without_deleting_sets() -> None:
    service = _service()

    response = _client(service).delete(
        f"/api/tenants/{_CHANNEL_ID}/active-roleplay", headers=_ACTION
    )

    assert response.status_code == 200
    assert response.json() == {
        "assistant_mode": "persona",
        "active_roleplay_revision_id": None,
    }
    service.use_persona.assert_awaited_once_with(_CHANNEL_ID)
    service.archive.assert_not_awaited()


def test_delete_set_archives_but_returns_its_state() -> None:
    service = _service()

    response = _client(service).delete(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets/{_SET_ID}", headers=_ACTION
    )

    assert response.status_code == 200
    assert response.json()["archived_at"] == _NOW.isoformat().replace("+00:00", "Z")
    service.archive.assert_awaited_once_with(_CHANNEL_ID, _SET_ID)


def test_rate_limiter_is_applied_before_mutation(monkeypatch) -> None:
    service = _service()
    limiter = MagicMock()
    limiter.require.side_effect = HTTPException(status_code=429, detail="Rate limit exceeded")
    monkeypatch.setattr(roleplay_router, "_mutation_limiter", limiter)

    response = _client(service).delete(
        f"/api/tenants/{_CHANNEL_ID}/active-roleplay", headers=_ACTION
    )

    assert response.status_code == 429
    service.use_persona.assert_not_awaited()


def test_export_returns_exact_revision_as_private_download() -> None:
    service = _service()

    response = _client(service).get(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-sets/{_SET_ID}/revisions/41/export"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.niibot.roleplay-character+json"
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in response.headers["content-disposition"]
    assert response.json()["format"] == "niibot.roleplay-character"
    service.export_revision.assert_awaited_once_with(_CHANNEL_ID, _SET_ID, 41)


def test_import_forwards_only_path_tenant_and_selected_result() -> None:
    service = _service()
    document = build_roleplay_character_export(
        display_name="月港守望者",
        package=sample_roleplay_package(),
        compiled=compile_roleplay_package(sample_roleplay_package()),
        exported_at=_NOW,
    )

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-imports",
        json={"mode": "copy", "character": document},
        headers=_ACTION,
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "copy"
    assert response.json()["reused"] is False
    assert response.json()["active_roleplay_revision_id"] is None
    service.import_character.assert_awaited_once_with(
        _CHANNEL_ID,
        mode="copy",
        character=document,
    )


def test_import_rejects_tenant_override_and_requires_action_header() -> None:
    service = _service()

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-imports",
        json={"mode": "copy", "character": {}, "channel_id": "channel-b"},
        headers=_ACTION,
    )
    missing_header = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-imports",
        json={"mode": "copy", "character": {}},
    )

    assert response.status_code == 422
    assert missing_header.status_code == 422
    service.import_character.assert_not_awaited()


def test_import_rejects_oversize_body_before_parsing_or_service_call() -> None:
    service = _service()
    body = b"{" + (b" " * MAX_PORTABLE_ROLEPLAY_BYTES) + b"}"

    response = _client(service).post(
        f"/api/tenants/{_CHANNEL_ID}/roleplay-imports",
        content=body,
        headers={**_ACTION, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ROLEPLAY.IMPORT_TOO_LARGE"
    service.import_character.assert_not_awaited()
