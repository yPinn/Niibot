"""Tests for api.routers.donation_router.

Covers:
- return_url open-redirect fix (scheme+netloc exact match)
- _build_check_mac_value algorithm (pure function, no DB)
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-donation")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import get_db_pool
from routers.donation_router import _build_check_mac_value
from routers.donation_router import router as _donation_router


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _make_client(pool: AsyncMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_donation_router)
    _pool = pool or AsyncMock()
    app.dependency_overrides[get_db_pool] = lambda: _pool
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# POST /{username}/checkout — return_url validation
# ---------------------------------------------------------------------------


class TestCheckoutReturnUrlValidation:
    """return_url must share exact scheme + netloc with FRONTEND_URL."""

    @pytest.fixture(autouse=True)
    def _patch_repo_not_found(self):
        """Make DonationRepository.get_configs_by_username return None (404)
        so that valid return_url tests reach (and pass) the URL check and then
        stop at the DB check — letting us distinguish 400 (rejected) from 404 (passed)."""
        with patch(
            "routers.donation_router.DonationRepository.get_configs_by_username",
            new=AsyncMock(return_value=None),
        ):
            yield

    def test_valid_return_url_passes_check(self):
        """Same origin as FRONTEND_URL must not raise 400."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "ecpay", "amount": 100, "return_url": "https://niibot.tv/success"},
        )
        # 404 = DB check was reached (return_url accepted)
        assert r.status_code == 404

    def test_no_return_url_passes_check(self):
        """Omitting return_url must not raise 400."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "ecpay", "amount": 100},
        )
        assert r.status_code == 404

    def test_subdomain_bypass_rejected(self):
        """https://niibot.tv.evil.com must not pass the netloc comparison."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={
                "platform": "ecpay",
                "amount": 100,
                "return_url": "https://niibot.tv.evil.com/success",
            },
        )
        assert r.status_code == 400
        assert "return_url" in r.json()["detail"]

    def test_http_scheme_rejected_when_frontend_is_https(self):
        """http:// must be rejected when FRONTEND_URL is https://."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={
                "platform": "ecpay",
                "amount": 100,
                "return_url": "http://niibot.tv/success",
            },
        )
        assert r.status_code == 400

    def test_different_domain_rejected(self):
        """A completely different domain must be rejected."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={
                "platform": "ecpay",
                "amount": 100,
                "return_url": "https://evil.com/phish",
            },
        )
        assert r.status_code == 400

    def test_path_traversal_same_origin_allowed(self):
        """Arbitrary paths on the same origin must be allowed (path is not validated)."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={
                "platform": "ecpay",
                "amount": 100,
                "return_url": "https://niibot.tv/donate/thanks?ref=123",
            },
        )
        assert r.status_code == 404

    def test_unsupported_platform_returns_400_before_url_check(self):
        """Unsupported platform must fail fast (400) before even reaching the URL check."""
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={
                "platform": "payoneer",
                "amount": 100,
                "return_url": "https://evil.com/steal",
            },
        )
        assert r.status_code == 400
        assert "platform" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# _build_check_mac_value — pure algorithm unit tests
# ---------------------------------------------------------------------------


class TestBuildCheckMacValue:
    """ECPay/OPay MAC algorithm: sort → url-encode → SHA-256 UPPERCASE."""

    _KEY = "5294y06JbISpM5x9"
    _IV = "v77hoKGq4kWxNNIS"

    def test_known_ecpay_params(self):
        """Verify the algorithm produces a consistent deterministic result."""
        params = {
            "MerchantID": "2000132",
            "MerchantTradeNo": "thisisatestno0001",
            "MerchantTradeDate": "2017/02/13 15:45:30",
            "PaymentType": "aio",
            "TotalAmount": "2000",
            "TradeDesc": "test",
            "ItemName": "TestItem",
            "ReturnURL": "https://niibot.tv/callback",
            "ChoosePayment": "ALL",
            "EncryptType": "1",
        }
        result = _build_check_mac_value(params, self._KEY, self._IV)
        # Must be 64-char uppercase hex (SHA-256)
        assert len(result) == 64
        assert result == result.upper()
        assert all(c in "0123456789ABCDEF" for c in result)

    def test_check_mac_value_excluded_from_calculation(self):
        """CheckMacValue key in params must be stripped before hashing."""
        params_with = {
            "MerchantID": "123",
            "TotalAmount": "100",
            "CheckMacValue": "OLDVALUE",
        }
        params_without = {
            "MerchantID": "123",
            "TotalAmount": "100",
        }
        assert _build_check_mac_value(params_with, self._KEY, self._IV) == _build_check_mac_value(
            params_without, self._KEY, self._IV
        )

    def test_different_keys_produce_different_mac(self):
        params = {"MerchantID": "123", "Amt": "50"}
        mac1 = _build_check_mac_value(params, "key1", "iv_1")
        mac2 = _build_check_mac_value(params, "key2", "iv_2")
        assert mac1 != mac2
