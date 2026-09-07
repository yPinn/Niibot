"""Tests for api.routers.donation_router.

Covers:
- return_url open-redirect guard (scheme+netloc exact match)
- checkout rate limit
- GET /public/{username}
- webhook amount validation (ECPay + NewebPay) via the unified /webhook/{platform}
- _extract_video_id helper

Pure crypto lives in test_payment_cmv.py / test_payment_mpg.py.
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
from routers.donation_router import router as _donation_router
from services.payment._cmv import build_check_mac_value
from services.payment._mpg import aes_encrypt, trade_sha256


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
        with patch(
            "routers.donation_router.DonationRepository.get_configs_by_username",
            new=AsyncMock(return_value=None),
        ):
            yield

    def test_valid_return_url_passes_check(self):
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "ecpay", "amount": 100, "return_url": "https://niibot.tv/success"},
        )
        assert r.status_code == 404

    def test_no_return_url_passes_check(self):
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "ecpay", "amount": 100},
        )
        assert r.status_code == 404

    def test_subdomain_bypass_rejected(self):
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
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "ecpay", "amount": 100, "return_url": "http://niibot.tv/success"},
        )
        assert r.status_code == 400

    def test_different_domain_rejected(self):
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "ecpay", "amount": 100, "return_url": "https://evil.com/phish"},
        )
        assert r.status_code == 400

    def test_path_traversal_same_origin_allowed(self):
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
        r = _make_client().post(
            "/api/donate/testuser/checkout",
            json={"platform": "payoneer", "amount": 100, "return_url": "https://evil.com/steal"},
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "DONATION.INVALID"


# ---------------------------------------------------------------------------
# POST /{username}/checkout — rate limit
# ---------------------------------------------------------------------------


class TestCheckoutRateLimit:
    def test_rate_limit_exceeded_returns_429(self):
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
        assert [p["platform"] for p in data["platforms"]] == ["ecpay"]

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
# POST /api/donate/webhook/ecpay — verification + amount validation
# ---------------------------------------------------------------------------

_KEY, _IV = "5294y06JbISpM5x9", "v77hoKGq4kWxNNIS"


def _order(amount: int = 200):
    o = AsyncMock()
    o.merchant_trade_no = "T001"
    o.user_id = "user1"
    o.amount = amount
    o.youtube_video_id = None
    o.channel_id = None
    o.message = None
    return o


def _config():
    c = AsyncMock()
    c.hash_key = _KEY
    c.hash_iv = _IV
    c.media_share_enabled = False
    return c


def _signed_ecpay_form(**fields: str) -> dict[str, str]:
    form = {"MerchantID": "2000132", "MerchantTradeNo": "T001", **fields}
    form["CheckMacValue"] = build_check_mac_value(form, _KEY, _IV)
    return form


class TestEcpayWebhook:
    def _post(self, form: dict[str, str], order_amount: int = 200):
        with (
            patch(
                "routers.donation_router.DonationRepository.get_order_by_trade_no",
                new=AsyncMock(return_value=_order(order_amount)),
            ),
            patch(
                "routers.donation_router.DonationRepository.get_config",
                new=AsyncMock(return_value=_config()),
            ),
            patch(
                "routers.donation_router.DonationRepository.mark_paid",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "routers.donation_router.DonationRepository.mark_failed",
                new=AsyncMock(return_value=None),
            ) as mark_failed,
        ):
            resp = _make_client().post("/api/donate/webhook/ecpay", data=form)
        return resp, mark_failed

    def test_matching_amount_acks_ok(self):
        resp, _ = self._post(_signed_ecpay_form(RtnCode="1", TradeAmt="200"), order_amount=200)
        assert resp.status_code == 200
        assert resp.text == "1|OK"

    def test_mismatched_amount_acks_error(self):
        resp, _ = self._post(_signed_ecpay_form(RtnCode="1", TradeAmt="999"), order_amount=200)
        assert resp.text == "0|Error"

    def test_missing_trade_amt_acks_error(self):
        resp, _ = self._post(_signed_ecpay_form(RtnCode="1"), order_amount=200)
        assert resp.text == "0|Error"

    def test_float_trade_amt_acks_error(self):
        resp, _ = self._post(_signed_ecpay_form(RtnCode="1", TradeAmt="200.50"), order_amount=200)
        assert resp.text == "0|Error"

    def test_failed_rtn_code_marks_failed_and_acks_ok(self):
        resp, mark_failed = self._post(_signed_ecpay_form(RtnCode="0", TradeAmt="200"))
        assert resp.text == "1|OK"
        mark_failed.assert_awaited_once()

    def test_bad_mac_acks_error(self):
        form = {
            "MerchantID": "2000132",
            "MerchantTradeNo": "T001",
            "RtnCode": "1",
            "TradeAmt": "200",
        }
        form["CheckMacValue"] = "DEADBEEF" * 8
        resp, _ = self._post(form)
        assert resp.text == "0|Error"

    def test_unknown_order_acks_error(self):
        form = _signed_ecpay_form(RtnCode="1", TradeAmt="200")
        with patch(
            "routers.donation_router.DonationRepository.get_order_by_trade_no",
            new=AsyncMock(return_value=None),
        ):
            resp = _make_client().post("/api/donate/webhook/ecpay", data=form)
        assert resp.text == "0|Error"

    def test_unknown_platform_acks_error(self):
        resp = _make_client().post("/api/donate/webhook/stripe", data={"x": "1"})
        assert resp.text == "0|Error"


# ---------------------------------------------------------------------------
# POST /api/donate/webhook/newebpay — amount validation
# ---------------------------------------------------------------------------


class TestNewebpayWebhookAmountValidation:
    _NB_KEY = "0123456789abcdef0123456789abcdef"  # 32 bytes
    _NB_IV = "abcdef0123456789"  # 16 bytes

    def _post(self, amt: int, order_amount: int = 200):
        trade_json = json.dumps({"Status": "SUCCESS", "MerchantOrderNo": "T001", "Amt": amt})
        trade_info = aes_encrypt(trade_json, self._NB_KEY, self._NB_IV)
        trade_sha = trade_sha256(trade_info, self._NB_KEY, self._NB_IV)

        config = AsyncMock()
        config.hash_key = self._NB_KEY
        config.hash_iv = self._NB_IV
        config.media_share_enabled = False

        with (
            patch(
                "routers.donation_router.DonationRepository.get_config_by_merchant_id",
                new=AsyncMock(return_value=config),
            ),
            patch(
                "routers.donation_router.DonationRepository.get_order_by_trade_no",
                new=AsyncMock(return_value=_order(order_amount)),
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
        assert resp.json() == {"status": "ok"}
        mark_paid.assert_awaited_once()

    def test_mismatched_amount_does_not_mark_paid(self):
        resp, mark_paid = self._post(amt=1, order_amount=200)
        assert resp.status_code == 200
        assert resp.json() == {"status": "error"}
        mark_paid.assert_not_awaited()


# ---------------------------------------------------------------------------
# _extract_video_id
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    def test_valid_youtube_url_returns_id(self):
        from routers.donation_router import _extract_video_id

        assert _extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ", True) == "dQw4w9WgXcQ"

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
