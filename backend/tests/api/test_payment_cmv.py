"""ECPay CheckMacValue — validated against the official test vectors in
``.claude/skills/ecpay/guides/13-checkmacvalue.md``.
"""

from __future__ import annotations

import pytest

from services.payment._cmv import (
    build_check_mac_value,
    ecpay_url_encode,
    verify_check_mac_value,
)

# Public ECPay test credentials (AIO / national logistics).
_AIO_KEY, _AIO_IV = "pwFHCqoQZGmho4w6", "EkRm7iFT261dpevs"
_LOG_KEY, _LOG_IV = "5294y06JbISpM5x9", "v77hoKGq4kWxNNIS"


class TestOfficialVectors:
    """Known-answer vectors straight from guides/13 — locks the algorithm."""

    def test_sha256_aio_vector(self):
        params = {
            "MerchantID": "3002607",
            "MerchantTradeNo": "Test1234567890",
            "MerchantTradeDate": "2025/01/01 12:00:00",
            "PaymentType": "aio",
            "TotalAmount": "100",
            "TradeDesc": "測試",
            "ItemName": "測試商品",
            "ReturnURL": "https://example.com/notify",
            "ChoosePayment": "ALL",
            "EncryptType": "1",
        }
        assert build_check_mac_value(params, _AIO_KEY, _AIO_IV) == (
            "291CBA324D31FB5A4BBBFDF2CFE5D32598524753AFD4959C3BF590C5B2F57FB2"
        )

    def test_apostrophe_vector(self):
        params = {"MerchantID": "3002607", "ItemName": "Tom's Shop", "TotalAmount": "100"}
        assert build_check_mac_value(params, _AIO_KEY, _AIO_IV) == (
            "CF0A3D4901D99459D8641516EC57210700E8A5C9AB26B1D021301E9CB93EF78D"
        )

    def test_md5_logistics_vector(self):
        params = {
            "MerchantID": "2000132",
            "LogisticsType": "CVS",
            "LogisticsSubType": "UNIMART",
            "MerchantTradeDate": "2025/01/01 12:00:00",
        }
        assert build_check_mac_value(params, _LOG_KEY, _LOG_IV, method="md5") == (
            "545E6146FD45BDA683C88454DB34CE8D"
        )


class TestTildeEncoding:
    """Regression lock for the ~ → %7e bug (donor messages contain tildes)."""

    def test_tilde_is_percent_encoded(self):
        assert ecpay_url_encode("a~b") == "a%7eb"

    def test_tilde_in_value_changes_the_mac(self):
        plain = {"MerchantID": "3002607", "CustomField2": "thanks yo", "TotalAmount": "100"}
        tilde = {"MerchantID": "3002607", "CustomField2": "thanks ~yo~", "TotalAmount": "100"}
        assert build_check_mac_value(plain, _AIO_KEY, _AIO_IV) != build_check_mac_value(
            tilde, _AIO_KEY, _AIO_IV
        )

    def test_tilde_vector_is_stable(self):
        params = {"MerchantID": "3002607", "CustomField2": "thanks ~yo~", "TotalAmount": "100"}
        assert build_check_mac_value(params, _AIO_KEY, _AIO_IV) == (
            "88BA5B9E9DE6DBC16F2BAC8B098085846459AC2D4579A81C0A4D13A0B991ED0B"
        )


class TestBuildCheckMacValue:
    def test_check_mac_value_excluded_from_calculation(self):
        with_cmv = {"MerchantID": "123", "TotalAmount": "100", "CheckMacValue": "OLD"}
        without = {"MerchantID": "123", "TotalAmount": "100"}
        assert build_check_mac_value(with_cmv, _AIO_KEY, _AIO_IV) == build_check_mac_value(
            without, _AIO_KEY, _AIO_IV
        )

    def test_result_is_uppercase_hex_64(self):
        result = build_check_mac_value({"A": "1"}, _AIO_KEY, _AIO_IV)
        assert len(result) == 64
        assert result == result.upper()
        assert all(c in "0123456789ABCDEF" for c in result)

    def test_different_keys_differ(self):
        params = {"MerchantID": "123", "Amt": "50"}
        assert build_check_mac_value(params, "key1", "iv_1") != build_check_mac_value(
            params, "key2", "iv_2"
        )


class TestVerifyCheckMacValue:
    def _params(self) -> dict[str, str]:
        return {"MerchantID": "2000132", "TotalAmount": "500", "TradeDesc": "test"}

    def test_correct_mac_true(self):
        p = self._params()
        form = {**p, "CheckMacValue": build_check_mac_value(p, _LOG_KEY, _LOG_IV)}
        assert verify_check_mac_value(form, _LOG_KEY, _LOG_IV) is True

    def test_lowercase_received_mac_accepted(self):
        p = self._params()
        form = {**p, "CheckMacValue": build_check_mac_value(p, _LOG_KEY, _LOG_IV).lower()}
        assert verify_check_mac_value(form, _LOG_KEY, _LOG_IV) is True

    def test_wrong_mac_false(self):
        form = {**self._params(), "CheckMacValue": "DEADBEEF" * 8}
        assert verify_check_mac_value(form, _LOG_KEY, _LOG_IV) is False

    def test_missing_mac_false(self):
        assert verify_check_mac_value(self._params(), _LOG_KEY, _LOG_IV) is False

    def test_wrong_key_false(self):
        p = self._params()
        form = {**p, "CheckMacValue": build_check_mac_value(p, _LOG_KEY, _LOG_IV)}
        assert verify_check_mac_value(form, "wrong_key", _LOG_IV) is False


@pytest.mark.parametrize("value", ["!*()", "a b c", "50%off", "https://x.tv/a?b=1"])
def test_encode_is_deterministic(value: str):
    assert ecpay_url_encode(value) == ecpay_url_encode(value)
