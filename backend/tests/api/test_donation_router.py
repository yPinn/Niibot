"""Tests for api.routers.donation_router.

Covers:
- return_url open-redirect fix (scheme+netloc exact match)
- _build_check_mac_value algorithm (pure function, no DB)
- _handle_payment_webhook amount validation
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
from routers.donation_router import (
    _build_check_mac_value,
    _handle_payment_webhook,
    _verify_webhook_mac,
)
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


# ---------------------------------------------------------------------------
# _verify_webhook_mac — constant-time MAC verification
# ---------------------------------------------------------------------------


class TestVerifyWebhookMac:
    """Verify hmac.compare_digest-based MAC check is correct and case-insensitive."""

    _KEY = "5294y06JbISpM5x9"
    _IV = "v77hoKGq4kWxNNIS"

    def _make_params(self) -> dict:
        return {"MerchantID": "2000132", "TotalAmount": "500", "TradeDesc": "test"}

    def test_correct_mac_returns_true(self):
        params = self._make_params()
        correct_mac = _build_check_mac_value(params, self._KEY, self._IV)
        form = {**params, "CheckMacValue": correct_mac}
        assert _verify_webhook_mac(form, self._KEY, self._IV) is True

    def test_wrong_mac_returns_false(self):
        params = self._make_params()
        form = {**params, "CheckMacValue": "DEADBEEF" * 8}
        assert _verify_webhook_mac(form, self._KEY, self._IV) is False

    def test_lowercase_received_mac_accepted(self):
        """Gateway may send lowercase hex; comparison must be case-insensitive."""
        params = self._make_params()
        correct_mac = _build_check_mac_value(params, self._KEY, self._IV)
        form = {**params, "CheckMacValue": correct_mac.lower()}
        assert _verify_webhook_mac(form, self._KEY, self._IV) is True

    def test_missing_check_mac_value_returns_false(self):
        params = self._make_params()
        assert _verify_webhook_mac(params, self._KEY, self._IV) is False

    def test_wrong_key_returns_false(self):
        params = self._make_params()
        correct_mac = _build_check_mac_value(params, self._KEY, self._IV)
        form = {**params, "CheckMacValue": correct_mac}
        assert _verify_webhook_mac(form, "wrong_key", self._IV) is False


# ---------------------------------------------------------------------------
# _handle_payment_webhook — amount validation
# ---------------------------------------------------------------------------


def _make_order(amount: int = 200):
    order = AsyncMock()
    order.merchant_trade_no = "T001"
    order.user_id = "user1"
    order.amount = amount
    order.youtube_video_id = None
    order.channel_id = None
    order.message = None
    return order


def _make_config(key: str = "testkey", iv: str = "testiv"):
    cfg = AsyncMock()
    cfg.hash_key = key
    cfg.hash_iv = iv
    cfg.media_share_enabled = False
    return cfg


@pytest.mark.asyncio
class TestWebhookAmountValidation:
    """_handle_payment_webhook must reject TradeAmt that doesn't match the stored order amount."""

    _BASE_FORM = {
        "MerchantTradeNo": "T001",
        "RtnCode": "1",
    }

    async def _call(self, form_data: dict, order_amount: int = 200) -> str:
        pool = AsyncMock()
        with (
            patch(
                "routers.donation_router.DonationRepository.get_order_by_trade_no",
                new=AsyncMock(return_value=_make_order(order_amount)),
            ),
            patch(
                "routers.donation_router.DonationRepository.get_config",
                new=AsyncMock(return_value=_make_config()),
            ),
            patch(
                "routers.donation_router._verify_webhook_mac",
                return_value=True,
            ),
            patch(
                "routers.donation_router.DonationRepository.mark_paid",
                new=AsyncMock(return_value=None),
            ),
        ):
            return await _handle_payment_webhook("ecpay", form_data, pool)

    async def test_matching_amount_returns_ok(self):
        form = {**self._BASE_FORM, "TradeAmt": "200"}
        result = await self._call(form, order_amount=200)
        assert result == "1|OK"

    async def test_mismatched_amount_returns_error(self):
        form = {**self._BASE_FORM, "TradeAmt": "999"}
        result = await self._call(form, order_amount=200)
        assert result == "0|Error"

    async def test_missing_trade_amt_returns_error(self):
        form = {**self._BASE_FORM}
        result = await self._call(form, order_amount=200)
        assert result == "0|Error"

    async def test_non_integer_trade_amt_returns_error(self):
        form = {**self._BASE_FORM, "TradeAmt": "abc"}
        result = await self._call(form, order_amount=200)
        assert result == "0|Error"

    async def test_float_string_trade_amt_returns_error(self):
        form = {**self._BASE_FORM, "TradeAmt": "200.50"}
        result = await self._call(form, order_amount=200)
        assert result == "0|Error"
