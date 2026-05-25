"""Application-level encryption for sensitive DB values.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache(maxsize=4)
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode())


def encrypt_value(plaintext: str, key: str) -> str:
    """Encrypt plaintext to a Fernet token string."""
    return _fernet(key).encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, key: str) -> str:
    """Decrypt a Fernet token. Raises InvalidToken if tampered or wrong key."""
    return _fernet(key).decrypt(ciphertext.encode()).decode()


def decrypt_or_passthrough(value: str | None, key: str | None) -> str | None:
    """Decrypt value when a key is present; fall back to plaintext on failure.

    The plaintext fallback covers the migration window where rows written before
    encryption was introduced still contain unencrypted values.
    """
    if value is None or not key:
        return value
    try:
        return decrypt_value(value, key)
    except Exception:
        return value
