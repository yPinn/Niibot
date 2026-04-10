"""Tests for api.routers.message_triggers_router.

Covers:
- POST /api/triggers/configs — regex pattern validated on create
- PUT  /api/triggers/configs/{name} — regex validated only when BOTH pattern
  AND match_type are provided in the body (the fix for the bypass bug)
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-triggers")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_channel_id, get_db_pool
from routers.message_triggers_router import router as _triggers_router

_CHANNEL_ID = "test-channel-123"
_TRIGGER_ROW = {
    "id": 1,
    "channel_id": _CHANNEL_ID,
    "trigger_name": "mytest",
    "match_type": "regex",
    "pattern": r"\d+",
    "case_sensitive": False,
    "response": "matched!",
    "min_role": "everyone",
    "cooldown": None,
    "priority": 0,
    "enabled": True,
    "usage_count": 0,
    "aliases": None,
    "created_at": None,
    "updated_at": None,
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _make_client(service_mock: MagicMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_triggers_router)

    pool = AsyncMock()
    app.dependency_overrides[get_db_pool] = lambda: pool
    app.dependency_overrides[get_current_channel_id] = lambda: _CHANNEL_ID

    if service_mock:
        # Inject the service mock via pool — but we patch at the class level below.
        pass

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# POST /api/triggers/configs — validation on CREATE
# ---------------------------------------------------------------------------


class TestCreateTriggerRegexValidation:
    def test_valid_regex_creates_trigger(self):
        """A syntactically valid regex must pass and call service.create_trigger."""
        import services.message_trigger_service as svc_mod

        mock_svc = MagicMock()
        mock_svc.create_trigger = AsyncMock(return_value=_TRIGGER_ROW)

        with MagicMock() as _patch:
            import unittest.mock as um

            with um.patch.object(
                svc_mod.MessageTriggerService, "create_trigger", mock_svc.create_trigger
            ):
                r = _make_client().post(
                    "/api/triggers/configs",
                    json={
                        "trigger_name": "mytest",
                        "match_type": "regex",
                        "pattern": r"\d+",
                        "response": "ok",
                    },
                )
        assert r.status_code == 201

    def test_invalid_regex_returns_400(self):
        """An invalid regex pattern must be rejected before reaching the service."""
        r = _make_client().post(
            "/api/triggers/configs",
            json={
                "trigger_name": "bad",
                "match_type": "regex",
                "pattern": "[invalid(",
                "response": "nope",
            },
        )
        assert r.status_code == 400
        assert "regex" in r.json()["detail"].lower()

    def test_regex_too_long_returns_400(self):
        """Regex patterns over 200 chars must be rejected."""
        long_pattern = "a" * 201
        r = _make_client().post(
            "/api/triggers/configs",
            json={
                "trigger_name": "toolong",
                "match_type": "regex",
                "pattern": long_pattern,
                "response": "no",
            },
        )
        assert r.status_code == 400
        assert "200" in r.json()["detail"]

    def test_non_regex_match_type_skips_validation(self):
        """startswith/contains/exact patterns are not regex-validated."""
        import unittest.mock as um

        import services.message_trigger_service as svc_mod

        row = {**_TRIGGER_ROW, "match_type": "startswith", "pattern": "[not-a-regex"}
        with um.patch.object(
            svc_mod.MessageTriggerService,
            "create_trigger",
            AsyncMock(return_value=row),
        ):
            r = _make_client().post(
                "/api/triggers/configs",
                json={
                    "trigger_name": "startswith_test",
                    "match_type": "startswith",
                    "pattern": "[not-a-regex",
                    "response": "ok",
                },
            )
        assert r.status_code == 201

    def test_exactly_200_char_regex_is_accepted(self):
        """Boundary: 200-char pattern must not be rejected (> 200 is the limit)."""
        import unittest.mock as um

        import services.message_trigger_service as svc_mod

        pattern = "a" * 200
        row = {**_TRIGGER_ROW, "pattern": pattern}
        with um.patch.object(
            svc_mod.MessageTriggerService,
            "create_trigger",
            AsyncMock(return_value=row),
        ):
            r = _make_client().post(
                "/api/triggers/configs",
                json={
                    "trigger_name": "boundary",
                    "match_type": "regex",
                    "pattern": pattern,
                    "response": "ok",
                },
            )
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# PUT /api/triggers/configs/{name} — validation on UPDATE
# ---------------------------------------------------------------------------


class TestUpdateTriggerRegexValidation:
    """The fix: validation runs only when BOTH pattern AND match_type are given."""

    def test_invalid_regex_with_match_type_returns_400(self):
        """Sending an invalid regex pattern WITH match_type=regex must be rejected."""
        r = _make_client().put(
            "/api/triggers/configs/mytest",
            json={"match_type": "regex", "pattern": "[invalid("},
        )
        assert r.status_code == 400
        assert "regex" in r.json()["detail"].lower()

    def test_pattern_only_no_match_type_skips_validation(self):
        """Sending only pattern (no match_type) must NOT validate as regex — old bypass fix."""
        import unittest.mock as um

        import services.message_trigger_service as svc_mod

        row = {**_TRIGGER_ROW, "pattern": "[invalid(", "match_type": "startswith"}
        with um.patch.object(
            svc_mod.MessageTriggerService,
            "update_trigger",
            AsyncMock(return_value=row),
        ):
            r = _make_client().put(
                "/api/triggers/configs/mytest",
                json={"pattern": "[invalid("},
            )
        # 200 = validation was skipped (pattern with no match_type)
        assert r.status_code == 200

    def test_match_type_only_no_pattern_skips_validation(self):
        """Sending only match_type=regex (no pattern) must not attempt validation."""
        import unittest.mock as um

        import services.message_trigger_service as svc_mod

        row = {**_TRIGGER_ROW, "match_type": "regex"}
        with um.patch.object(
            svc_mod.MessageTriggerService,
            "update_trigger",
            AsyncMock(return_value=row),
        ):
            r = _make_client().put(
                "/api/triggers/configs/mytest",
                json={"match_type": "regex"},
            )
        assert r.status_code == 200

    def test_valid_regex_with_match_type_passes(self):
        """A valid regex with explicit match_type=regex must be accepted."""
        import unittest.mock as um

        import services.message_trigger_service as svc_mod

        row = {**_TRIGGER_ROW, "pattern": r"\d+", "match_type": "regex"}
        with um.patch.object(
            svc_mod.MessageTriggerService,
            "update_trigger",
            AsyncMock(return_value=row),
        ):
            r = _make_client().put(
                "/api/triggers/configs/mytest",
                json={"match_type": "regex", "pattern": r"\d+"},
            )
        assert r.status_code == 200

    def test_regex_too_long_with_match_type_returns_400(self):
        """Oversized regex in an update must also be rejected."""
        r = _make_client().put(
            "/api/triggers/configs/mytest",
            json={"match_type": "regex", "pattern": "x" * 201},
        )
        assert r.status_code == 400
