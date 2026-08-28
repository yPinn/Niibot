"""Tests for middleware and global exception handler wired up in app.py.

Uses create_app() with a patched no-op lifespan so that no real DB
connection or background tasks are started.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-middleware-secret-key-32chars")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import create_app
from core.config import get_settings
from shared.errors import NotFoundError

_ALLOWED_ORIGIN = "https://niibot.tv"


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Full app via create_app() with a no-op lifespan + two test-only routes."""
    with patch("app.lifespan", _no_lifespan):
        test_app = create_app()

    @test_app.get("/_test/ok")
    async def _ok():
        return {"ok": True}

    @test_app.get("/_test/error")
    async def _error():
        raise RuntimeError("deliberate test error")

    @test_app.get("/_test/app-error")
    async def _app_error():
        raise NotFoundError(user_message="找不到這個東西", context={"secret_id": "leaky-12345"})

    class _Body(BaseModel):
        count: int

    @test_app.post("/_test/validate")
    async def _validate(body: _Body):
        return {"count": body.count}

    return TestClient(test_app, raise_server_exceptions=False)


# ── Security headers ──────────────────────────────────────────────────────────


class TestSecurityHeaders:
    def test_csp_header(self, client: TestClient):
        r = client.get("/_test/ok")
        assert r.headers["Content-Security-Policy"] == "default-src 'none'"

    def test_x_content_type_options(self, client: TestClient):
        r = client.get("/_test/ok")
        assert r.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self, client: TestClient):
        r = client.get("/_test/ok")
        assert r.headers["X-Frame-Options"] == "DENY"

    def test_referrer_policy(self, client: TestClient):
        r = client.get("/_test/ok")
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client: TestClient):
        r = client.get("/_test/ok")
        assert r.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


# ── Request ID middleware ─────────────────────────────────────────────────────


class TestRequestId:
    def test_request_id_generated_when_absent(self, client: TestClient):
        r = client.get("/_test/ok")
        rid = r.headers.get("X-Request-ID", "")
        assert rid, "X-Request-ID must be present in response"
        uuid.UUID(rid)  # raises ValueError if not a valid UUID

    def test_upstream_request_id_echoed(self, client: TestClient):
        upstream_id = "my-upstream-trace-id"
        r = client.get("/_test/ok", headers={"X-Request-ID": upstream_id})
        assert r.headers["X-Request-ID"] == upstream_id

    def test_different_requests_get_unique_ids(self, client: TestClient):
        r1 = client.get("/_test/ok")
        r2 = client.get("/_test/ok")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


# ── Global exception handler ──────────────────────────────────────────────────


class TestGlobalExceptionHandler:
    def test_unhandled_exception_returns_500(self, client: TestClient):
        r = client.get("/_test/error")
        assert r.status_code == 500

    def test_error_body_envelope(self, client: TestClient):
        r = client.get("/_test/error", headers={"X-Request-ID": "rid-500"})
        body = r.json()
        assert body["detail"] == body["error"]["message"]
        assert body["error"]["code"] == "INTERNAL.UNEXPECTED"
        assert body["error"]["request_id"] == "rid-500"
        # generic, no internals leaked
        assert "deliberate test error" not in r.text

    def test_error_response_includes_request_id(self, client: TestClient):
        r = client.get("/_test/error")
        assert r.headers.get("X-Request-ID"), "500 response must include X-Request-ID"

    def test_upstream_request_id_echoed_on_error(self, client: TestClient):
        trace_id = "trace-abc-123"
        r = client.get("/_test/error", headers={"X-Request-ID": trace_id})
        assert r.status_code == 500
        assert r.headers["X-Request-ID"] == trace_id


class TestAppErrorHandler:
    def test_status_and_envelope(self, client: TestClient):
        r = client.get("/_test/app-error", headers={"X-Request-ID": "rid-ae"})
        assert r.status_code == 404
        body = r.json()
        assert body["detail"] == "找不到這個東西"
        assert body["error"] == {
            "code": "INTERNAL.NOT_FOUND",
            "message": "找不到這個東西",
            "request_id": "rid-ae",
            "fields": None,
        }

    def test_context_not_leaked(self, client: TestClient):
        r = client.get("/_test/app-error")
        assert "leaky-12345" not in r.text


class TestValidationHandler:
    def test_detail_is_string_not_list(self, client: TestClient):
        r = client.post("/_test/validate", json={"count": "not-an-int"})
        assert r.status_code == 422
        body = r.json()
        assert isinstance(body["detail"], str)  # B3: never a list
        assert body["error"]["code"] == "VALIDATION.INVALID_INPUT"
        # pydantic's English message must not reach the client
        assert "Input should be" not in r.text


class TestCors:
    def test_expose_headers_on_ok(self, client: TestClient):
        r = client.get("/_test/ok", headers={"Origin": _ALLOWED_ORIGIN})
        assert r.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
        assert "x-request-id" in r.headers.get("access-control-expose-headers", "").lower()

    def test_cors_headers_on_500(self, client: TestClient):
        # B2: a cross-origin frontend must be able to read the error body.
        r = client.get("/_test/error", headers={"Origin": _ALLOWED_ORIGIN})
        assert r.status_code == 500
        assert r.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN

    def test_cors_headers_on_504_path_present_for_app_error(self, client: TestClient):
        r = client.get("/_test/app-error", headers={"Origin": _ALLOWED_ORIGIN})
        assert r.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
