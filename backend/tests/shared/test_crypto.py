"""Unit tests for shared.crypto."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from shared.crypto import decrypt_or_passthrough, decrypt_value, encrypt_value

_KEY = Fernet.generate_key().decode()


class TestEncryptDecrypt:
    def test_roundtrip(self):
        ciphertext = encrypt_value("secret123", _KEY)
        assert ciphertext != "secret123"  # stored token is not plaintext
        assert decrypt_value(ciphertext, _KEY) == "secret123"

    def test_different_ciphertexts_each_call(self):
        """Fernet uses a random nonce — same plaintext produces different tokens."""
        c1 = encrypt_value("same", _KEY)
        c2 = encrypt_value("same", _KEY)
        assert c1 != c2

    def test_wrong_key_raises(self):
        other_key = Fernet.generate_key().decode()
        ciphertext = encrypt_value("secret", _KEY)
        with pytest.raises((InvalidToken, Exception)):
            decrypt_value(ciphertext, other_key)

    def test_empty_string_roundtrip(self):
        assert decrypt_value(encrypt_value("", _KEY), _KEY) == ""


class TestDecryptOrPassthrough:
    def test_none_value_returns_none(self):
        assert decrypt_or_passthrough(None, _KEY) is None

    def test_none_key_returns_plaintext(self):
        assert decrypt_or_passthrough("abc", None) == "abc"

    def test_empty_key_returns_plaintext(self):
        assert decrypt_or_passthrough("abc", "") == "abc"

    def test_decrypts_valid_token(self):
        token = encrypt_value("mysecret", _KEY)
        assert decrypt_or_passthrough(token, _KEY) == "mysecret"

    def test_plaintext_migration_fallback(self):
        """Pre-encryption plaintext values should pass through without error."""
        assert decrypt_or_passthrough("plaintext_legacy_value", _KEY) == "plaintext_legacy_value"
