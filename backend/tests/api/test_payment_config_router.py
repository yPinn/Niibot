"""Tests for api.routers.payment_config_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_current_user_id, get_db_pool, require_activated
from core.error_handlers import register_exception_handlers
from routers.payment_config_router import router as _pc_router

USER_ID = "user-abc"
_NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _config(platform: str = "ecpay", has_hash: bool = True) -> MagicMock:
    c = MagicMock()
    c.platform = platform
    c.merchant_id = "MERCHANT001"
    c.has_hash = has_hash  # for list_configs (PaymentConfigSummary)
    c.hash_key = "key" if has_hash else None  # for upsert/get_config (PaymentConfig)
    c.hash_iv = "iv" if has_hash else None
    c.min_amount = 30
    c.media_share_enabled = False
    c.enabled = True
    c.updated_at = _NOW
    return c


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client() -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_pc_router)
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[require_activated] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _make_client_not_activated() -> TestClient:
    """Client where require_activated rejects the caller, for gate tests."""
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_pc_router)
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()

    def _reject() -> None:
        raise HTTPException(status_code=403, detail="Account not activated")

    app.dependency_overrides[require_activated] = _reject
    return TestClient(app, raise_server_exceptions=False)


# ── GET /api/payment-configs ──────────────────────────────────────────────────


class TestListPaymentConfigs:
    def test_returns_list_with_has_hash(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.list_configs = AsyncMock(return_value=[_config("ecpay")])
            r = _make_client().get("/api/payment-configs")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["has_hash"] is True
        assert "hash_key" not in r.json()[0]

    def test_empty_list_returns_200(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.list_configs = AsyncMock(return_value=[])
            r = _make_client().get("/api/payment-configs")
        assert r.status_code == 200
        assert r.json() == []

    def test_repo_error_returns_500(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.list_configs = AsyncMock(side_effect=RuntimeError)
            r = _make_client().get("/api/payment-configs")
        assert r.status_code == 500


# ── PUT /api/payment-configs/{platform} ──────────────────────────────────────


class TestUpsertPaymentConfig:
    def test_upsert_ecpay_with_hash(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.upsert_config = AsyncMock(return_value=_config("ecpay"))
            r = _make_client().put(
                "/api/payment-configs/ecpay",
                json={
                    "merchant_id": "M001",
                    "hash_key": "key",
                    "hash_iv": "iv",
                    "min_amount": 30,
                    "media_share_enabled": False,
                    "enabled": True,
                },
            )
        assert r.status_code == 200
        assert r.json()["platform"] == "ecpay"

    def test_ecpay_without_hash_no_existing_returns_400(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.get_config = AsyncMock(return_value=None)
            r = _make_client().put(
                "/api/payment-configs/ecpay",
                json={"merchant_id": "M001", "min_amount": 30},
            )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "PAYMENT_CONFIG.INVALID"
        assert "hash_key" not in r.text

    def test_ecpay_without_hash_keeps_existing(self):
        """Omitting hash on update preserves the stored keys (keep-existing-hash)."""
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            existing = _config("ecpay", has_hash=True)
            mock_repo.return_value.get_config = AsyncMock(return_value=existing)
            mock_repo.return_value.upsert_config = AsyncMock(return_value=_config("ecpay"))
            r = _make_client().put(
                "/api/payment-configs/ecpay",
                json={"merchant_id": "M001", "min_amount": 50},
            )
        assert r.status_code == 200
        # upsert_config must have been called with the preserved key values
        call_kwargs = mock_repo.return_value.upsert_config.call_args.kwargs
        assert call_kwargs["hash_key"] == "key"
        assert call_kwargs["hash_iv"] == "iv"
        assert call_kwargs["min_amount"] == 50

    def test_invalid_platform_returns_400(self):
        r = _make_client().put(
            "/api/payment-configs/stripe",
            json={"merchant_id": "M001", "min_amount": 30},
        )
        assert r.status_code == 400

    def test_paypal_no_hash_required(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            cfg = _config("paypal", has_hash=False)
            mock_repo.return_value.upsert_config = AsyncMock(return_value=cfg)
            r = _make_client().put(
                "/api/payment-configs/paypal",
                json={"merchant_id": "PP001", "min_amount": 10},
            )
        assert r.status_code == 200

    def test_repo_error_returns_500(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.upsert_config = AsyncMock(side_effect=RuntimeError)
            r = _make_client().put(
                "/api/payment-configs/ecpay",
                json={"merchant_id": "M001", "hash_key": "k", "hash_iv": "i"},
            )
        assert r.status_code == 500


# ── DELETE /api/payment-configs/{platform} ───────────────────────────────────


class TestDeletePaymentConfig:
    def test_deletes_and_returns_ok(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.delete_config = AsyncMock(return_value=True)
            r = _make_client().delete("/api/payment-configs/ecpay")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_not_found_returns_404(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.delete_config = AsyncMock(return_value=False)
            r = _make_client().delete("/api/payment-configs/paypal")
        assert r.status_code == 404

    def test_invalid_platform_returns_400(self):
        r = _make_client().delete("/api/payment-configs/stripe")
        assert r.status_code == 400

    def test_repo_error_returns_500(self):
        with patch("routers.payment_config_router.DonationRepository") as mock_repo:
            mock_repo.return_value.delete_config = AsyncMock(side_effect=RuntimeError)
            r = _make_client().delete("/api/payment-configs/ecpay")
        assert r.status_code == 500


# ── require_activated gate ────────────────────────────────────────────────────


class TestActivationGate:
    def test_list_rejected_when_not_activated(self):
        r = _make_client_not_activated().get("/api/payment-configs")
        assert r.status_code == 403

    def test_upsert_rejected_when_not_activated(self):
        r = _make_client_not_activated().put(
            "/api/payment-configs/ecpay",
            json={"merchant_id": "M1", "hash_key": "k", "hash_iv": "iv"},
        )
        assert r.status_code == 403

    def test_delete_rejected_when_not_activated(self):
        r = _make_client_not_activated().delete("/api/payment-configs/ecpay")
        assert r.status_code == 403
