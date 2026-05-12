"""Repository for activation_codes table."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

_EXPIRES_HOURS = 72


def _generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class ActivationCodeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(self, platform: str, platform_user_id: str) -> str:
        """Generate and store a hashed 6-digit OTP. Returns the raw code string."""
        code = _generate_otp()
        code_hash = _hash_code(code)
        expires_at = datetime.now(UTC) + timedelta(hours=_EXPIRES_HOURS)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Invalidate any prior unused codes for this user so only one is active.
                await conn.execute(
                    "DELETE FROM activation_codes"
                    " WHERE platform = $1 AND platform_user_id = $2 AND used_at IS NULL",
                    platform,
                    platform_user_id,
                )
                await conn.execute(
                    "INSERT INTO activation_codes"
                    " (code_hash, code_plain, platform, platform_user_id, expires_at)"
                    " VALUES ($1, $2, $3, $4, $5)",
                    code_hash,
                    code,
                    platform,
                    platform_user_id,
                    expires_at,
                )

        return code

    async def get_plain_code(self, platform: str, platform_user_id: str) -> str | None:
        """Return the pending plain-text code for a user, or None if no valid code exists."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT code_plain FROM activation_codes"
                " WHERE platform = $1 AND platform_user_id = $2"
                "   AND used_at IS NULL AND expires_at > NOW()"
                " ORDER BY expires_at DESC LIMIT 1",
                platform,
                platform_user_id,
            )
        return row["code_plain"] if row else None

    async def redeem(
        self,
        code: str,
        platform: str,
        platform_user_id: str,
        user_id: str,
    ) -> bool:
        """Validate and consume a code. Returns True on success, False otherwise."""
        code_hash = _hash_code(code)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT code_hash FROM activation_codes"
                    " WHERE code_hash = $1"
                    "   AND platform = $2"
                    "   AND platform_user_id = $3"
                    "   AND used_at IS NULL"
                    "   AND expires_at > NOW()"
                    " FOR UPDATE",
                    code_hash,
                    platform,
                    platform_user_id,
                )
                if not row:
                    return False

                await conn.execute(
                    "UPDATE activation_codes"
                    " SET used_at = NOW(), used_by_user_id = $2::uuid"
                    " WHERE code_hash = $1",
                    code_hash,
                    user_id,
                )
                await conn.execute(
                    "UPDATE users SET is_activated = TRUE WHERE id = $1::uuid",
                    user_id,
                )

        return True

    async def invalidate(self, platform: str, platform_user_id: str) -> bool:
        """Delete the unused code for a user. Returns True if a row was deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM activation_codes"
                " WHERE platform = $1 AND platform_user_id = $2 AND used_at IS NULL",
                platform,
                platform_user_id,
            )
        return result != "DELETE 0"
