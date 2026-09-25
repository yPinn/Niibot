"""Tests for api.routers.discord_webhook_router."""

from __future__ import annotations

import json
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from routers.discord_webhook_router import (
    _dispatch_event,
    _verify_signature,
)
from routers.discord_webhook_router import (
    router as _discord_router,
)

# ── Ed25519 helpers ───────────────────────────────────────────────────────────


def _gen_keypair() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private_key, pub_bytes.hex()


def _sign(private_key: Ed25519PrivateKey, timestamp: str, body: bytes) -> str:
    return private_key.sign(timestamp.encode() + body).hex()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(public_key_hex: str = "") -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_discord_router)
    return TestClient(app, raise_server_exceptions=False)


# ── _verify_signature unit tests ──────────────────────────────────────────────


class TestVerifySignature:
    def test_valid_signature_returns_true(self):
        private_key, pub_hex = _gen_keypair()
        ts = "1234567890"
        body = b'{"type":1}'
        sig_hex = _sign(private_key, ts, body)
        assert _verify_signature(pub_hex, sig_hex, ts, body) is True

    def test_wrong_body_returns_false(self):
        private_key, pub_hex = _gen_keypair()
        ts = "1234567890"
        body = b'{"type":1}'
        sig_hex = _sign(private_key, ts, body)
        assert _verify_signature(pub_hex, sig_hex, ts, b"tampered") is False

    def test_wrong_timestamp_returns_false(self):
        private_key, pub_hex = _gen_keypair()
        ts = "1234567890"
        body = b'{"type":1}'
        sig_hex = _sign(private_key, ts, body)
        assert _verify_signature(pub_hex, sig_hex, "9999999999", body) is False

    def test_invalid_hex_returns_false(self):
        _, pub_hex = _gen_keypair()
        assert _verify_signature(pub_hex, "not-hex", "ts", b"body") is False

    def test_wrong_key_returns_false(self):
        private_key1, _ = _gen_keypair()
        _, pub_hex2 = _gen_keypair()
        ts = "1234567890"
        body = b'{"type":0}'
        sig_hex = _sign(private_key1, ts, body)
        assert _verify_signature(pub_hex2, sig_hex, ts, body) is False


# ── _dispatch_event unit tests ────────────────────────────────────────────────


class TestDispatchEvent:
    def test_application_authorized_guild(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="routers.discord_webhook_router"):
            _dispatch_event(
                "APPLICATION_AUTHORIZED",
                {"guild": {"id": "g1", "name": "TestGuild"}, "user": {"username": "admin"}},
            )
        assert "TestGuild" in caplog.text

    def test_application_authorized_user_install(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="routers.discord_webhook_router"):
            _dispatch_event(
                "APPLICATION_AUTHORIZED",
                {"guild": None, "user": {"username": "tester", "id": "u1"}},
            )
        assert "tester" in caplog.text

    def test_entitlement_create(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="routers.discord_webhook_router"):
            _dispatch_event(
                "ENTITLEMENT_CREATE",
                {"id": "ent1", "sku_id": "sku1", "user_id": "u1", "guild_id": None},
            )
        assert "ent1" in caplog.text

    def test_entitlement_update(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="routers.discord_webhook_router"):
            _dispatch_event(
                "ENTITLEMENT_UPDATE",
                {"id": "ent2", "sku_id": "sku1", "ends_at": "2025-01-01"},
            )
        assert "ent2" in caplog.text

    def test_entitlement_delete(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="routers.discord_webhook_router"):
            _dispatch_event(
                "ENTITLEMENT_DELETE",
                {"id": "ent3", "sku_id": "sku1", "user_id": "u1"},
            )
        assert "ent3" in caplog.text

    def test_unknown_event_type_is_silently_ignored(self):
        # Should not raise
        _dispatch_event("FUTURE_UNKNOWN_EVENT", {"data": "x"})

    def test_deauthorized_event(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="routers.discord_webhook_router"):
            _dispatch_event(
                "APPLICATION_DEAUTHORIZED",
                {"user": {"username": "leaver", "id": "u9"}},
            )
        assert "leaver" in caplog.text


# ── POST /api/discord/webhook ─────────────────────────────────────────────────


class TestDiscordWebhookEndpoint:
    def _post(
        self,
        client: TestClient,
        payload: dict | None,
        *,
        private_key: Ed25519PrivateKey | None = None,
        pub_hex: str = "",
        timestamp: str = "1234567890",
        bad_sig: bool = False,
        missing_sig: bool = False,
        raw_body: bytes | None = None,
    ):
        body = raw_body if raw_body is not None else json.dumps(payload).encode()
        if missing_sig:
            headers = {}
        elif bad_sig or private_key is None:
            headers = {
                "X-Signature-Ed25519": "deadbeef" * 16,
                "X-Signature-Timestamp": timestamp,
            }
        else:
            sig = _sign(private_key, timestamp, body)
            headers = {
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": timestamp,
            }
        return client.post("/api/discord/webhook", content=body, headers=headers)

    def test_no_public_key_configured_returns_501(self):
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": None})(),
        ):
            r = self._post(client, {"type": 1}, missing_sig=True)
        assert r.status_code == 501

    def test_missing_signature_headers_returns_401(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(client, {"type": 1}, missing_sig=True)
        assert r.status_code == 401

    def test_invalid_signature_returns_401(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(client, {"type": 1}, private_key=private_key, bad_sig=True)
        assert r.status_code == 401

    def test_ping_returns_empty_204(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(client, {"type": 0}, private_key=private_key, pub_hex=pub_hex)
        assert r.status_code == 204
        assert r.content == b""
        assert r.headers["content-type"] == "application/json"

    def test_event_returns_empty_204(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        payload = {
            "type": 1,
            "event": {
                "type": "APPLICATION_AUTHORIZED",
                "data": {
                    "guild": {"id": "g1", "name": "TestGuild"},
                    "user": {"username": "admin"},
                },
            },
        }
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(client, payload, private_key=private_key, pub_hex=pub_hex)
        assert r.status_code == 204
        assert r.content == b""
        assert r.headers["content-type"] == "application/json"

    def test_unknown_payload_type_returns_400(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(client, {"type": 99}, private_key=private_key, pub_hex=pub_hex)
        assert r.status_code == 400

    def test_invalid_event_envelope_returns_400(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(
                client,
                {"type": 1, "event": "not-an-object"},
                private_key=private_key,
                pub_hex=pub_hex,
            )
        assert r.status_code == 400

    def test_invalid_json_returns_400_after_signature_verification(self):
        private_key, pub_hex = _gen_keypair()
        client = _make_client()
        with patch(
            "routers.discord_webhook_router.get_settings",
            return_value=type("S", (), {"discord_public_key": pub_hex})(),
        ):
            r = self._post(
                client,
                None,
                private_key=private_key,
                pub_hex=pub_hex,
                raw_body=b"not-json",
            )
        assert r.status_code == 400
