"""Dataclass models for donation/payment tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PaymentConfigSummary:
    """Lightweight list-query result — no raw key material loaded into memory."""

    user_id: str
    platform: str
    merchant_id: str
    has_hash: bool
    min_amount: int
    media_share_enabled: bool
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PaymentConfig:
    """Per-streamer, per-platform merchant configuration."""

    user_id: str
    platform: str  # ecpay | opay | paypal
    merchant_id: str  # MerchantID (ECPay/OPay) or PayPal URL/email
    hash_key: str | None  # ECPay/OPay only
    hash_iv: str | None  # ECPay/OPay only
    min_amount: int = 30
    media_share_enabled: bool = False
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class DonationOrder:
    """Single donation transaction record."""

    id: str
    user_id: str  # streamer's UUID
    channel_id: str  # Twitch platform_user_id (for video queue)
    platform: str
    merchant_trade_no: str  # 20-char alphanumeric sent to payment gateway
    amount: int
    message: str | None
    youtube_video_id: str | None  # 11-char YT ID
    status: str  # pending | paid | failed
    created_at: datetime | None = None
    updated_at: datetime | None = None
