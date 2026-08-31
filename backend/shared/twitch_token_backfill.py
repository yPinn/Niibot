"""Bounded data-migration helpers for Twitch token encryption."""

from __future__ import annotations

from typing import Protocol

from shared.twitch_token_crypto import encrypt_twitch_token


class _BackfillConnection(Protocol):
    async def fetch(self, query: str, *args: object) -> list: ...

    async def execute(self, query: str, *args: object) -> str: ...


async def backfill_twitch_token_batch(
    conn: _BackfillConnection, *, key: str, batch_size: int = 100
) -> int:
    """Encrypt at most one locked batch of legacy token rows.

    The caller owns the transaction so each batch commits independently. The
    version-zero predicate on both SELECT and UPDATE makes concurrent workers
    idempotent and prevents overwriting a token refreshed during the backfill.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")

    rows = await conn.fetch(
        """
        SELECT user_id, token_type, token, refresh
          FROM tokens
         WHERE encryption_version = 0
         ORDER BY user_id, token_type
         LIMIT $1
         FOR UPDATE SKIP LOCKED
        """,
        batch_size,
    )
    updated = 0
    for row in rows:
        encrypted_token, version = encrypt_twitch_token(row["token"], key)
        encrypted_refresh, refresh_version = encrypt_twitch_token(row["refresh"], key)
        if version != refresh_version:  # pragma: no cover - defensive future-version guard
            raise RuntimeError("Twitch token and refresh encryption versions diverged")
        status = await conn.execute(
            """
            UPDATE tokens
               SET token = $1,
                   refresh = $2,
                   encryption_version = $3,
                   updated_at = NOW()
             WHERE user_id = $4
               AND token_type = $5
               AND encryption_version = 0
            """,
            encrypted_token,
            encrypted_refresh,
            version,
            row["user_id"],
            row["token_type"],
        )
        if status == "UPDATE 1":
            updated += 1
    return updated
