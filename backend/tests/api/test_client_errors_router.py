"""Tests for api.routers.client_errors_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-client-errors-secret-key-32chars")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_auth_service, get_db_pool
from core.error_handlers import register_exception_handlers
from routers import client_errors_router
from routers.client_errors_router import _per_fingerprint, _per_ip
from routers.client_errors_router import router as _router

_VALID = {
    "kind": "react",
    "fingerprint": "abc123",
    "message": "Cannot read properties of undefined",
    "url": "https://niibot.tv/dashboard",
    "stack": "at Foo (bundle.js:1:2)",
    "request_id": "req-xyz",
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    _per_ip._log.clear()
    _per_fingerprint._log.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def insert_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    m = AsyncMock()
    monkeypatch.setattr(client_errors_router.ClientErrorRepository, "insert", m, raising=True)
    return m


def _client() -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_router)
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    auth = AsyncMock()
    auth.verify_token = lambda _t: None
    app.dependency_overrides[get_auth_service] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


class TestReport:
    def test_unauthenticated_accepted(self, insert_mock: AsyncMock):
        r = _client().post("/api/client-errors", json=_VALID)
        assert r.status_code == 202
        assert r.content == b""
        insert_mock.assert_awaited_once()

    def test_oversized_message_is_dropped(self, insert_mock: AsyncMock):
        bad = {**_VALID, "message": "x" * 5000}
        r = _client().post("/api/client-errors", json=bad)
        assert r.status_code == 202
        insert_mock.assert_not_awaited()

    def test_content_length_over_ceiling_is_dropped(self, insert_mock: AsyncMock):
        r = _client().post(
            "/api/client-errors",
            json=_VALID,
            headers={"Content-Length": "40000"},
        )
        assert r.status_code == 202
        insert_mock.assert_not_awaited()

    def test_bad_kind_is_dropped(self, insert_mock: AsyncMock):
        r = _client().post("/api/client-errors", json={**_VALID, "kind": "weird"})
        assert r.status_code == 202
        insert_mock.assert_not_awaited()

    def test_per_ip_rate_limit(self, insert_mock: AsyncMock):
        c = _client()
        for i in range(20):
            c.post("/api/client-errors", json={**_VALID, "fingerprint": f"fp{i}"})
        assert insert_mock.await_count == 20
        r = c.post("/api/client-errors", json={**_VALID, "fingerprint": "fp-extra"})
        assert r.status_code == 202
        assert insert_mock.await_count == 20  # not inserted

    def test_per_fingerprint_rate_limit(self, insert_mock: AsyncMock):
        c = _client()
        for _ in range(5):
            c.post("/api/client-errors", json=_VALID)
        # 3 allowed by the per-fingerprint limiter, rest dropped
        assert insert_mock.await_count == 3

    def test_internal_error_still_returns_202(self, insert_mock: AsyncMock):
        insert_mock.side_effect = RuntimeError("db down")
        r = _client().post("/api/client-errors", json=_VALID)
        assert r.status_code == 202

    def test_text_plain_body_is_parsed(self, insert_mock: AsyncMock):
        import json

        r = _client().post(
            "/api/client-errors",
            content=json.dumps(_VALID),
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )
        assert r.status_code == 202
        insert_mock.assert_awaited_once()
