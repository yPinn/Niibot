"""Unit tests for shared.repositories.donation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from shared.repositories.donation import DonationRepository

_ENC_KEY = Fernet.generate_key().decode()


def _make_pool(*, execute: str = "UPDATE 1") -> tuple:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=execute)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)

    return pool, conn


def _make_config_row(hash_key: str | None = "raw_key", hash_iv: str | None = "raw_iv") -> dict:
    return {
        "user_id": "user-1",
        "platform": "ecpay",
        "merchant_id": "M001",
        "hash_key": hash_key,
        "hash_iv": hash_iv,
        "min_amount": 30,
        "media_share_enabled": False,
        "enabled": True,
        "created_at": None,
        "updated_at": None,
    }


# ---------------------------------------------------------------------------
# mark_failed — only transitions pending → failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMarkFailed:
    async def test_sql_includes_pending_guard(self):
        """SQL must include AND status = 'pending' to prevent downgrading paid orders."""
        pool, conn = _make_pool()
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-001")

        sql: str = conn.execute.call_args[0][0]
        assert "pending" in sql

    async def test_passes_trade_no_as_parameter(self):
        pool, conn = _make_pool()
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-abc")

        assert "trade-abc" in conn.execute.call_args[0]

    async def test_sets_status_to_failed(self):
        pool, conn = _make_pool()
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-001")

        sql: str = conn.execute.call_args[0][0]
        assert "failed" in sql

    async def test_no_op_when_already_paid(self):
        """UPDATE with AND status='pending' silently skips paid orders (UPDATE 0 is not an error)."""
        pool, conn = _make_pool(execute="UPDATE 0")
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-paid")

        conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# DonationRepository encryption / decryption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEncryption:
    async def test_get_config_decrypts_hash(self):
        """get_config decrypts stored Fernet tokens back to plaintext."""
        from shared.crypto import encrypt_value

        encrypted_key = encrypt_value("real_hash_key", _ENC_KEY)
        encrypted_iv = encrypt_value("real_hash_iv", _ENC_KEY)

        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=_make_config_row(encrypted_key, encrypted_iv))

        repo = DonationRepository(pool, _ENC_KEY)
        config = await repo.get_config("user-1", "ecpay")

        assert config is not None
        assert config.hash_key == "real_hash_key"
        assert config.hash_iv == "real_hash_iv"

    async def test_get_config_no_key_passthrough(self):
        """Without encryption key, stored values are returned as-is."""
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=_make_config_row("raw_key", "raw_iv"))

        repo = DonationRepository(pool, encryption_key=None)
        config = await repo.get_config("user-1", "ecpay")

        assert config is not None
        assert config.hash_key == "raw_key"
        assert config.hash_iv == "raw_iv"

    async def test_upsert_config_encrypts_before_write(self):
        """upsert_config stores encrypted Fernet tokens, not raw plaintext."""
        from shared.crypto import decrypt_value

        pool, conn = _make_pool()
        # fetchrow returns None so upsert raises — that's fine; we only inspect call args
        conn.fetchrow = AsyncMock(return_value=None)

        repo = DonationRepository(pool, _ENC_KEY)
        try:
            await repo.upsert_config("u", "ecpay", "M", "plaintext_key", "plaintext_iv")
        except Exception:
            pass  # PaymentConfig(**dict(None)) will raise; we only care about call args

        call_args = conn.fetchrow.call_args[0]
        # Positional args: sql, user_id, platform, merchant_id, hash_key, hash_iv, ...
        written_key = call_args[4]
        written_iv = call_args[5]

        assert written_key != "plaintext_key"
        assert written_iv != "plaintext_iv"
        assert decrypt_value(written_key, _ENC_KEY) == "plaintext_key"
        assert decrypt_value(written_iv, _ENC_KEY) == "plaintext_iv"

    async def test_get_config_plaintext_migration_fallback(self):
        """Plaintext values stored before encryption was enabled are returned without error."""
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=_make_config_row("plaintext_key", "plaintext_iv"))

        repo = DonationRepository(pool, _ENC_KEY)
        config = await repo.get_config("user-1", "ecpay")

        assert config is not None
        # Plaintext passes through (not a valid Fernet token, fallback kicks in)
        assert config.hash_key == "plaintext_key"
        assert config.hash_iv == "plaintext_iv"
