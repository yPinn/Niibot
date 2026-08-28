"""Tests for api.routers.donation_router.

Covers:
- return_url open-redirect fix (scheme+netloc exact match)
- _build_check_mac_value algorithm (pure function, no DB)
- _handle_payment_webhook amount validation
"""

from __future__ import annotations

import json
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
from core.error_handlers import register_exception_handlers
from routers.donation_router import (
    _build_check_mac_value,
    _handle_payment_webhook,
    _newebpay_aes_encrypt,
    _newebpay_sha256,
    _verify_webhook_mac,
)
from routers.donation_router import router as _donation_router


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _make_client(pool: AsyncMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
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
        assert r.json()["error"]["code"] == "DONATION.INVALID"

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
        assert r.json()["error"]["code"] == "DONATION.INVALID"


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


# ---------------------------------------------------------------------------
# POST /api/donate/webhook/newebpay — amount validation (parity with ECPay/OPay)
# ---------------------------------------------------------------------------


class TestNewebpayWebhookAmountValidation:
    """webhook_newebpay must reject a decrypted Amt that doesn't match the order."""

    # NewebPay hash_key must be 32 bytes and hash_iv 16 bytes (AES-256-CBC).
    _KEY = "0123456789abcdef0123456789abcdef"
    _IV = "abcdef0123456789"

    def _post(self, amt: int, order_amount: int = 200):
        trade_json = json.dumps({"Status": "SUCCESS", "MerchantOrderNo": "T001", "Amt": amt})
        trade_info = _newebpay_aes_encrypt(trade_json, self._KEY, self._IV)
        trade_sha = _newebpay_sha256(trade_info, self._KEY, self._IV)

        config = _make_config(self._KEY, self._IV)
        order = _make_order(order_amount)

        with (
            patch(
                "routers.donation_router.DonationRepository.get_config_by_merchant_id",
                new=AsyncMock(return_value=config),
            ),
            patch(
                "routers.donation_router.DonationRepository.get_order_by_trade_no",
                new=AsyncMock(return_value=order),
            ),
            patch(
                "routers.donation_router.DonationRepository.mark_paid",
                new=AsyncMock(return_value=None),
            ) as mark_paid,
        ):
            resp = _make_client().post(
                "/api/donate/webhook/newebpay",
                data={
                    "Status": "SUCCESS",
                    "MerchantID": "MERCH1",
                    "TradeInfo": trade_info,
                    "TradeSha": trade_sha,
                    "Version": "2.0",
                },
            )
        return resp, mark_paid

    def test_matching_amount_marks_paid(self):
        resp, mark_paid = self._post(amt=200, order_amount=200)
        assert resp.status_code == 200
        mark_paid.assert_awaited_once()

    def test_mismatched_amount_does_not_mark_paid(self):
        resp, mark_paid = self._post(amt=1, order_amount=200)
        assert resp.status_code == 200
        assert resp.json() == {"status": "error"}
        mark_paid.assert_not_awaited()


# ---------------------------------------------------------------------------
# POST /api/donate/{username}/checkout — checkout rate limit
# ---------------------------------------------------------------------------


class TestCheckoutRateLimit:
    def test_rate_limit_exceeded_returns_429(self):
        """_checkout_limiter.require() raising 429 must propagate from checkout."""
        from routers.donation_router import _checkout_limiter

        with patch.object(_checkout_limiter, "allow", return_value=False):
            r = _make_client().post(
                "/api/donate/testuser/checkout",
                json={"platform": "ecpay", "amount": 100, "return_url": "https://niibot.tv/done"},
            )

        assert r.status_code == 429


# ---------------------------------------------------------------------------
# GET /api/donate/public/{username}
# ---------------------------------------------------------------------------


class TestGetPublicDonateInfo:
    def test_returns_enabled_platforms(self):
        cfg = AsyncMock()
        cfg.platform = "ecpay"
        cfg.min_amount = 50
        cfg.media_share_enabled = False
        cfg.enabled = True

        with patch(
            "routers.donation_router.DonationRepository.get_configs_by_username",
            new=AsyncMock(return_value=("user1", "ch1", [cfg])),
        ):
            r = _make_client().get("/api/donate/public/testuser")
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "testuser"
        assert len(data["platforms"]) == 1
        assert data["platforms"][0]["platform"] == "ecpay"

    def test_excludes_disabled_platforms(self):
        enabled_cfg = AsyncMock()
        enabled_cfg.platform = "ecpay"
        enabled_cfg.min_amount = 50
        enabled_cfg.media_share_enabled = False
        enabled_cfg.enabled = True

        disabled_cfg = AsyncMock()
        disabled_cfg.platform = "opay"
        disabled_cfg.enabled = False

        with patch(
            "routers.donation_router.DonationRepository.get_configs_by_username",
            new=AsyncMock(return_value=("user1", "ch1", [enabled_cfg, disabled_cfg])),
        ):
            r = _make_client().get("/api/donate/public/testuser")
        assert r.status_code == 200
        platforms = [p["platform"] for p in r.json()["platforms"]]
        assert "ecpay" in platforms
        assert "opay" not in platforms

    def test_streamer_not_found_returns_404(self):
        with patch(
            "routers.donation_router.DonationRepository.get_configs_by_username",
            new=AsyncMock(return_value=None),
        ):
            r = _make_client().get("/api/donate/public/unknownuser")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# _pkcs7_pad / _pkcs7_unpad — crypto primitives
# ---------------------------------------------------------------------------


class TestPkcs7:
    def test_pad_short_input(self):
        from routers.donation_router import _pkcs7_pad, _pkcs7_unpad

        original = b"hello"
        padded = _pkcs7_pad(original)
        assert len(padded) % 16 == 0
        assert _pkcs7_unpad(padded) == original

    def test_pad_exact_block_size_adds_full_block(self):
        from routers.donation_router import _pkcs7_pad, _pkcs7_unpad

        original = b"A" * 16
        padded = _pkcs7_pad(original)
        assert len(padded) == 32
        assert _pkcs7_unpad(padded) == original

    def test_unpad_invalid_length_raises(self):
        from routers.donation_router import _pkcs7_unpad

        with pytest.raises(ValueError):
            _pkcs7_unpad(b"\x00" * 16)  # pad byte 0 is invalid

    def test_unpad_empty_raises(self):
        from routers.donation_router import _pkcs7_unpad

        with pytest.raises(ValueError):
            _pkcs7_unpad(b"")

    def test_unpad_wrong_padding_bytes_raises(self):
        from routers.donation_router import _pkcs7_unpad

        # Last byte says 3 but padding bytes are inconsistent
        bad = b"hello world!!\x03\x03\x04"
        with pytest.raises(ValueError):
            _pkcs7_unpad(bad)


# ---------------------------------------------------------------------------
# _extract_video_id — YouTube URL extraction helper
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    def test_valid_youtube_url_returns_id(self):
        from routers.donation_router import _extract_video_id

        vid = _extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ", True)
        assert vid == "dQw4w9WgXcQ"

    def test_media_share_disabled_returns_none(self):
        from routers.donation_router import _extract_video_id

        assert _extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ", False) is None

    def test_no_url_returns_none(self):
        from routers.donation_router import _extract_video_id

        assert _extract_video_id(None, True) is None

    def test_invalid_url_raises_400(self):
        from routers.donation_router import DonationInvalidError, _extract_video_id

        with pytest.raises(DonationInvalidError) as exc_info:
            _extract_video_id("https://example.com/not-yt", True)
        assert exc_info.value.http_status == 400


# ---------------------------------------------------------------------------
# _newebpay_aes_encrypt / _newebpay_sha256 — NewebPay crypto
# ---------------------------------------------------------------------------


class TestNewebpayCrypto:
    _KEY = "12345678901234567890123456789012"  # 32 bytes
    _IV = "1234567890123456"  # 16 bytes

    def test_encrypt_decrypt_roundtrip(self):
        from routers.donation_router import _newebpay_aes_decrypt, _newebpay_aes_encrypt

        plaintext = "MerchantID=abc&Amt=100"
        encrypted = _newebpay_aes_encrypt(plaintext, self._KEY, self._IV)
        decrypted = _newebpay_aes_decrypt(encrypted, self._KEY, self._IV)
        assert decrypted == plaintext

    def test_sha256_produces_uppercase_hex(self):
        from routers.donation_router import _newebpay_sha256

        result = _newebpay_sha256("somehex", self._KEY, self._IV)
        assert result == result.upper()
        assert len(result) == 64
