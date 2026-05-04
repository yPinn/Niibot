"""Repository for user_payment_configs and donation_orders tables."""

from __future__ import annotations

import logging
import secrets
import string
import time

import asyncpg

from shared.models.donation import DonationOrder, PaymentConfig

LOGGER: logging.Logger = logging.getLogger(__name__)

_PAYMENT_CONFIG_COLS = (
    "user_id, platform, merchant_id, hash_key, hash_iv, "
    "min_amount, media_share_enabled, enabled, created_at, updated_at"
)

_DONATION_ORDER_COLS = (
    "id, user_id, channel_id, platform, merchant_trade_no, "
    "amount, message, youtube_video_id, status, created_at, updated_at"
)


def generate_trade_no() -> str:
    """Generate a unique 20-char alphanumeric MerchantTradeNo.

    Format: NII + 10-digit unix timestamp + 7 random uppercase alphanumeric.
    Safe for ECPay/OPay (alphanumeric only, max 20 chars).
    """
    ts = str(int(time.time()))
    rand = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(7))
    return f"NII{ts}{rand}"


class DonationRepository:
    """SQL operations for payment configs and donation orders."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ============================================================
    # Payment Config Methods
    # ============================================================

    async def list_configs(self, user_id: str) -> list[PaymentConfig]:
        """List all payment platform configs for a streamer."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_PAYMENT_CONFIG_COLS} FROM user_payment_configs "
                "WHERE user_id = $1 ORDER BY platform",
                user_id,
            )
            return [PaymentConfig(**dict(r)) for r in rows]

    async def get_config(self, user_id: str, platform: str) -> PaymentConfig | None:
        """Get a single platform config for a streamer."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_PAYMENT_CONFIG_COLS} FROM user_payment_configs "
                "WHERE user_id = $1 AND platform = $2",
                user_id,
                platform,
            )
            return PaymentConfig(**dict(row)) if row else None

    async def upsert_config(
        self,
        user_id: str,
        platform: str,
        merchant_id: str,
        hash_key: str | None,
        hash_iv: str | None,
        min_amount: int = 30,
        media_share_enabled: bool = False,
        enabled: bool = True,
    ) -> PaymentConfig:
        """Insert or update a payment platform config."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO user_payment_configs
                    (user_id, platform, merchant_id, hash_key, hash_iv,
                     min_amount, media_share_enabled, enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id, platform) DO UPDATE SET
                    merchant_id         = EXCLUDED.merchant_id,
                    hash_key            = EXCLUDED.hash_key,
                    hash_iv             = EXCLUDED.hash_iv,
                    min_amount          = EXCLUDED.min_amount,
                    media_share_enabled = EXCLUDED.media_share_enabled,
                    enabled             = EXCLUDED.enabled,
                    updated_at          = NOW()
                RETURNING {_PAYMENT_CONFIG_COLS}
                """,
                user_id,
                platform,
                merchant_id,
                hash_key,
                hash_iv,
                min_amount,
                media_share_enabled,
                enabled,
            )
            return PaymentConfig(**dict(row))

    async def delete_config(self, user_id: str, platform: str) -> bool:
        """Delete a payment platform config. Returns True if a row was deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_payment_configs WHERE user_id = $1 AND platform = $2",
                user_id,
                platform,
            )
            return result == "DELETE 1"

    async def get_configs_by_username(
        self, username: str
    ) -> tuple[str, str, list[PaymentConfig]] | None:
        """Look up enabled payment configs by Twitch username.

        Returns (user_id, channel_id, configs) or None if user not found.
        channel_id is the Twitch platform_user_id (used for video queue).
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ula.user_id::text, ula.platform_user_id AS channel_id
                FROM user_linked_accounts ula
                WHERE ula.platform = 'twitch'
                  AND LOWER(ula.username) = LOWER($1)
                """,
                username,
            )
            if not row:
                return None

            user_id = row["user_id"]
            channel_id = row["channel_id"]

            configs = await conn.fetch(
                f"SELECT {_PAYMENT_CONFIG_COLS} FROM user_payment_configs "
                "WHERE user_id = $1 AND enabled = TRUE ORDER BY platform",
                user_id,
            )
            return user_id, channel_id, [PaymentConfig(**dict(r)) for r in configs]

    async def get_config_by_merchant_id(
        self, platform: str, merchant_id: str
    ) -> PaymentConfig | None:
        """Look up a payment config by platform + merchant_id.

        Used by NewebPay webhook to resolve credentials from the incoming MerchantID.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_PAYMENT_CONFIG_COLS} FROM user_payment_configs "
                "WHERE platform = $1 AND merchant_id = $2 LIMIT 1",
                platform,
                merchant_id,
            )
            return PaymentConfig(**dict(row)) if row else None

    # ============================================================
    # Donation Order Methods
    # ============================================================

    async def create_order(
        self,
        user_id: str,
        channel_id: str,
        platform: str,
        merchant_trade_no: str,
        amount: int,
        message: str | None,
        youtube_video_id: str | None,
    ) -> DonationOrder:
        """Insert a new pending donation order."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO donation_orders
                    (user_id, channel_id, platform, merchant_trade_no,
                     amount, message, youtube_video_id, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                RETURNING {_DONATION_ORDER_COLS}
                """,
                user_id,
                channel_id,
                platform,
                merchant_trade_no,
                amount,
                message,
                youtube_video_id,
            )
            return DonationOrder(**dict(row))

    async def get_order_by_trade_no(self, merchant_trade_no: str) -> DonationOrder | None:
        """Look up an order by MerchantTradeNo (used in webhook lookup)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_DONATION_ORDER_COLS} FROM donation_orders WHERE merchant_trade_no = $1",
                merchant_trade_no,
            )
            return DonationOrder(**dict(row)) if row else None

    async def mark_paid(self, merchant_trade_no: str) -> DonationOrder | None:
        """Mark an order as paid. Returns the updated order."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE donation_orders
                SET status = 'paid', updated_at = NOW()
                WHERE merchant_trade_no = $1 AND status = 'pending'
                RETURNING {_DONATION_ORDER_COLS}
                """,
                merchant_trade_no,
            )
            return DonationOrder(**dict(row)) if row else None

    async def mark_failed(self, merchant_trade_no: str) -> None:
        """Mark a pending order as failed. No-op if already paid or failed."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE donation_orders SET status = 'failed', updated_at = NOW() "
                "WHERE merchant_trade_no = $1 AND status = 'pending'",
                merchant_trade_no,
            )
