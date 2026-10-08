"""Tests for api.routers.admin.rate_limits."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import require_owner
from routers.admin import rate_limits as module

_TWITCH_LIMITS = [
    {
        "name": "bot.helix",
        "group": "twitch",
        "limit": 720,
        "window_seconds": 60.0,
        "used": 3,
        "keys": 1,
    }
]


def _client(handler) -> TestClient:
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[require_owner] = lambda: "owner"
    real = httpx.AsyncClient

    def fake_client(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    patcher = patch.object(module.httpx, "AsyncClient", side_effect=fake_client)
    patcher.start()
    client = TestClient(app)
    client.__dict__["_patcher"] = patcher
    return client


def test_relays_bot_limits_and_reports_offline_bots_as_null() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        settings = module.get_settings()
        if str(request.url).startswith(settings.twitch_bot_url):
            return httpx.Response(200, json={"rate_limits": _TWITCH_LIMITS})
        raise httpx.ConnectError("down")

    client = _client(handler)
    try:
        r = client.get("/rate-limits")
    finally:
        client.__dict__["_patcher"].stop()
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["api"], list)
    assert body["twitch"] == _TWITCH_LIMITS
    assert body["discord"] is None


def test_requires_owner() -> None:
    app = FastAPI()
    app.include_router(module.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/rate-limits").status_code in (401, 403)
