"""NewebPay MPG crypto primitives (moved from test_donation_router)."""

from __future__ import annotations

import pytest

from services.payment._mpg import (
    aes_decrypt,
    aes_encrypt,
    pkcs7_pad,
    pkcs7_unpad,
    trade_sha256,
)

_KEY = "12345678901234567890123456789012"  # 32 bytes (AES-256)
_IV = "1234567890123456"  # 16 bytes


class TestPkcs7:
    def test_pad_short_input(self):
        original = b"hello"
        padded = pkcs7_pad(original)
        assert len(padded) % 16 == 0
        assert pkcs7_unpad(padded) == original

    def test_pad_exact_block_adds_full_block(self):
        original = b"A" * 16
        padded = pkcs7_pad(original)
        assert len(padded) == 32
        assert pkcs7_unpad(padded) == original

    def test_unpad_invalid_length_raises(self):
        with pytest.raises(ValueError):
            pkcs7_unpad(b"\x00" * 16)

    def test_unpad_empty_raises(self):
        with pytest.raises(ValueError):
            pkcs7_unpad(b"")

    def test_unpad_wrong_padding_bytes_raises(self):
        with pytest.raises(ValueError):
            pkcs7_unpad(b"hello world!!\x03\x03\x04")


class TestAes:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "MerchantID=abc&Amt=100"
        assert aes_decrypt(aes_encrypt(plaintext, _KEY, _IV), _KEY, _IV) == plaintext

    def test_ciphertext_is_lowercase_hex(self):
        enc = aes_encrypt("x", _KEY, _IV)
        assert enc == enc.lower()
        assert all(c in "0123456789abcdef" for c in enc)


class TestTradeSha:
    def test_uppercase_hex_64(self):
        result = trade_sha256("somehex", _KEY, _IV)
        assert result == result.upper()
        assert len(result) == 64
