"""Tests for api.routers.admin.client_errors."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-admin-client-errors-secret-key-32c")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import get_db_pool, require_owner
from core.error_handlers import register_exception_handlers
from routers.admin.client_errors import router as _router

_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)

_GROUP_ROW = {
    "fingerprint": "abc123",
    "count": 7,
    "first_seen": _NOW,
    "last_seen": _NOW,
    "kind": "react",
    "message": "Cannot read properties of undefined",
    "route": "/dashboard",
    "error_code": None,
    "http_status": None,
    "app_version": "1.2.3",
    "request_id": "req-xyz",
}

_EVENT_ROW = {
    "occurred_at": _NOW,
    "kind": "react",
    "message": "Cannot read properties of undefined",
    "stack": "at Foo (bundle.js:1:2)",
    "component_stack": "in Foo\nin App",
    "url": "https://niibot.tv/dashboard",
    "route": "/dashboard",
    "request_id": "req-xyz",
    "error_code": None,
    "http_status": None,
    "user_id": None,
    "user_agent": "Mozilla/5.0",
    "app_version": "1.2.3",
}


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _pool(rows: list[dict]) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool, conn


def _client(rows: list[dict]) -> tuple[TestClient, AsyncMock]:
    pool, conn = _pool(rows)
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_router)
    app.dependency_overrides[get_db_pool] = lambda: pool
    app.dependency_overrides[require_owner] = lambda: "owner"
    return TestClient(app, raise_server_exceptions=False), conn


class TestListClientErrors:
    def test_returns_grouped_rows(self):
        client, conn = _client([_GROUP_ROW])
        r = client.get("/client-errors")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["fingerprint"] == "abc123"
        assert body[0]["count"] == 7
        assert body[0]["request_id"] == "req-xyz"

    def test_passes_filters_to_repo(self):
        client, conn = _client([])
        r = client.get("/client-errors?since_hours=24&kind=api&limit=10")
        assert r.status_code == 200
        args = conn.fetch.await_args.args
        # (sql, since_hours, kind, limit)
        assert args[1] == 24
        assert args[2] == "api"
        assert args[3] == 10

    def test_rejects_bad_kind(self):
        client, _ = _client([])
        assert client.get("/client-errors?kind=weird").status_code == 422

    def test_rejects_since_hours_over_retention(self):
        client, _ = _client([])
        assert client.get("/client-errors?since_hours=999").status_code == 422


class TestGetEvents:
    def test_returns_raw_events(self):
        client, conn = _client([_EVENT_ROW])
        r = client.get("/client-errors/abc123")
        assert r.status_code == 200
        body = r.json()
        assert body[0]["stack"] == "at Foo (bundle.js:1:2)"
        assert body[0]["component_stack"] == "in Foo\nin App"
        assert conn.fetch.await_args.args[1] == "abc123"

    def test_stringifies_user_id(self):
        row = {**_EVENT_ROW, "user_id": "00000000-0000-0000-0000-000000000001"}
        client, _ = _client([row])
        r = client.get("/client-errors/abc123")
        assert r.json()[0]["user_id"] == "00000000-0000-0000-0000-000000000001"
