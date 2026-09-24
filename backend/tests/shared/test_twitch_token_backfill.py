"""Unit contracts for the bounded Twitch token encryption backfill."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from shared.twitch_token_backfill import (
    backfill_twitch_token_batch,
    repair_twitch_token_envelope_batch,
)
from shared.twitch_token_crypto import decrypt_twitch_token, encrypt_twitch_token

_KEY = Fernet.generate_key().decode()


@pytest.mark.asyncio
async def test_backfill_encrypts_one_bounded_batch_without_logging_secrets():
    conn = AsyncMock()
    conn.fetch.return_value = [
        {
            "user_id": "user-1",
            "token_type": "bot",
            "token": "access-secret",
            "refresh": "refresh-secret",
        }
    ]
    conn.execute.return_value = "UPDATE 1"

    updated = await backfill_twitch_token_batch(conn, key=_KEY, batch_size=25)

    assert updated == 1
    fetch_sql, fetch_limit = conn.fetch.call_args.args
    assert "FOR UPDATE SKIP LOCKED" in fetch_sql
    assert "encryption_version = 0" in fetch_sql
    assert fetch_limit == 25

    update_args = conn.execute.call_args.args
    assert "encryption_version = 0" in update_args[0]
    assert "access-secret" not in update_args[1:]
    assert "refresh-secret" not in update_args[1:]
    assert decrypt_twitch_token(update_args[1], version=1, key=_KEY) == "access-secret"
    assert decrypt_twitch_token(update_args[2], version=1, key=_KEY) == "refresh-secret"


@pytest.mark.asyncio
async def test_backfill_returns_zero_without_writes_when_complete():
    conn = AsyncMock()
    conn.fetch.return_value = []

    updated = await backfill_twitch_token_batch(conn, key=_KEY, batch_size=100)

    assert updated == 0
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_rejects_unbounded_batch_sizes():
    conn = AsyncMock()

    with pytest.raises(ValueError, match="batch_size"):
        await backfill_twitch_token_batch(conn, key=_KEY, batch_size=0)
    with pytest.raises(ValueError, match="batch_size"):
        await backfill_twitch_token_batch(conn, key=_KEY, batch_size=1001)


@pytest.mark.asyncio
async def test_repair_encrypts_version_one_values_missing_their_envelopes():
    conn = AsyncMock()
    conn.fetch.return_value = [
        {
            "user_id": "bot-1",
            "token_type": "bot",
            "token": "access-secret",
            "refresh": "refresh-secret",
        }
    ]
    conn.execute.return_value = "UPDATE 1"

    updated = await repair_twitch_token_envelope_batch(conn, key=_KEY, batch_size=25)

    assert updated == 1
    fetch_sql, fetch_limit = conn.fetch.call_args.args
    assert "FOR UPDATE SKIP LOCKED" in fetch_sql
    assert "encryption_version = 1" in fetch_sql
    assert "NOT LIKE 'v1:%'" in fetch_sql
    assert fetch_limit == 25

    update_args = conn.execute.call_args.args
    assert "encryption_version = 1" in update_args[0]
    assert "access-secret" not in update_args[1:]
    assert "refresh-secret" not in update_args[1:]
    assert decrypt_twitch_token(update_args[1], version=1, key=_KEY) == "access-secret"
    assert decrypt_twitch_token(update_args[2], version=1, key=_KEY) == "refresh-secret"


@pytest.mark.asyncio
async def test_repair_preserves_and_validates_an_existing_envelope():
    conn = AsyncMock()
    encrypted_access, _ = encrypt_twitch_token("access-secret", _KEY)
    conn.fetch.return_value = [
        {
            "user_id": "bot-1",
            "token_type": "bot",
            "token": encrypted_access,
            "refresh": "refresh-secret",
        }
    ]
    conn.execute.return_value = "UPDATE 1"

    updated = await repair_twitch_token_envelope_batch(conn, key=_KEY)

    assert updated == 1
    update_args = conn.execute.call_args.args
    assert update_args[1] == encrypted_access
    assert decrypt_twitch_token(update_args[2], version=1, key=_KEY) == "refresh-secret"


@pytest.mark.asyncio
async def test_repair_returns_zero_without_writes_when_no_envelopes_are_missing():
    conn = AsyncMock()
    conn.fetch.return_value = []

    updated = await repair_twitch_token_envelope_batch(conn, key=_KEY)

    assert updated == 0
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_rejects_unbounded_batch_sizes():
    conn = AsyncMock()

    with pytest.raises(ValueError, match="batch_size"):
        await repair_twitch_token_envelope_batch(conn, key=_KEY, batch_size=0)
    with pytest.raises(ValueError, match="batch_size"):
        await repair_twitch_token_envelope_batch(conn, key=_KEY, batch_size=1001)
