"""Versioned, fail-closed encryption for Twitch OAuth credentials."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from shared.errors import ServiceUnavailableError

CURRENT_TWITCH_TOKEN_ENCRYPTION_VERSION = 1
_V1_PREFIX = "v1:"


class TwitchTokenEncryptionError(ValueError):
    """Raised when a Twitch credential cannot be safely decoded."""


class TwitchTokenEnvelopeError(TwitchTokenEncryptionError):
    """A versioned credential is missing its required storage envelope."""


class TwitchTokenEncryptionNotConfiguredError(ServiceUnavailableError):
    """Missing Twitch credential encryption configuration."""

    code = "TWITCH_AUTHORIZATION.NOT_CONFIGURED"
    user_message = "Twitch 授權設定尚未完成，請聯絡管理員"


def require_twitch_token_encryption_key(key: str | None) -> str:
    """Return the configured key or reject token lifecycle operations."""
    if not key:
        raise TwitchTokenEncryptionNotConfiguredError()
    return key


def encrypt_twitch_token(plaintext: str, key: str) -> tuple[str, int]:
    """Return a v1 envelope and its persisted encryption version."""
    if not key:
        raise TwitchTokenEncryptionError("TWITCH_TOKEN_ENCRYPTION_KEY is not configured")

    encrypted = Fernet(key.encode()).encrypt(plaintext.encode()).decode()
    return f"{_V1_PREFIX}{encrypted}", CURRENT_TWITCH_TOKEN_ENCRYPTION_VERSION


def decrypt_twitch_token(value: str, *, version: int, key: str | None) -> str:
    """Decode a Twitch credential according to its explicit row version.

    Version zero is the bounded expand/backfill state. It never attempts to
    guess whether a value is encrypted. Version one is strict and fails closed
    for missing keys, malformed envelopes, tampering, or wrong keys.
    """
    if version == 0:
        return value
    if version != CURRENT_TWITCH_TOKEN_ENCRYPTION_VERSION:
        raise TwitchTokenEncryptionError(f"Unsupported Twitch token encryption version: {version}")
    if not key:
        raise TwitchTokenEncryptionError("TWITCH_TOKEN_ENCRYPTION_KEY is not configured")
    if not value.startswith(_V1_PREFIX):
        raise TwitchTokenEnvelopeError("Encrypted Twitch token is missing the v1 envelope")

    ciphertext = value.removeprefix(_V1_PREFIX)
    try:
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise TwitchTokenEncryptionError(
            "Stored Twitch token ciphertext could not be decrypted"
        ) from exc
