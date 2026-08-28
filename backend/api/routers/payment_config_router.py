"""Payment config management endpoints (authenticated).

Streamers use these to store their ECPay/OPay/PayPal merchant credentials.
Credentials are stored server-side; hash_key/hash_iv are never returned raw.
"""

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import get_current_user_id, get_db_pool, require_activated
from shared.errors import InvalidInputError, NotFoundError
from shared.repositories.donation import DonationRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment-configs", tags=["payment-configs"])

_VALID_PLATFORMS = {"ecpay", "opay", "paypal", "newebpay"}


class PaymentConfigNotFoundError(NotFoundError):
    code = "PAYMENT_CONFIG.NOT_FOUND"
    user_message = "找不到這個金流設定"


class PaymentConfigInvalidError(InvalidInputError):
    code = "PAYMENT_CONFIG.INVALID"
    user_message = "金流設定有誤，請檢查後再試"


class PaymentConfigUpsert(BaseModel):
    merchant_id: str = Field(..., min_length=1, max_length=100)
    hash_key: str | None = Field(default=None, max_length=200)
    hash_iv: str | None = Field(default=None, max_length=200)
    min_amount: int = Field(default=30, ge=1, le=99999)
    media_share_enabled: bool = False
    enabled: bool = True


class PaymentConfigResponse(BaseModel):
    platform: str
    merchant_id: str
    has_hash: bool  # True if hash_key is stored (never expose raw value)
    min_amount: int
    media_share_enabled: bool
    enabled: bool
    updated_at: datetime | None = None


@router.get("", response_model=list[PaymentConfigResponse])
async def list_payment_configs(
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
    _: None = Depends(require_activated),
) -> list[PaymentConfigResponse]:
    """List all payment platform configs for the authenticated streamer."""
    repo = DonationRepository(pool)
    configs = await repo.list_configs(user_id)
    return [
        PaymentConfigResponse(
            platform=c.platform,
            merchant_id=c.merchant_id,
            has_hash=c.has_hash,
            min_amount=c.min_amount,
            media_share_enabled=c.media_share_enabled,
            enabled=c.enabled,
            updated_at=c.updated_at,
        )
        for c in configs
    ]


@router.put("/{platform}", response_model=PaymentConfigResponse)
async def upsert_payment_config(
    platform: str,
    body: PaymentConfigUpsert,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
    _: None = Depends(require_activated),
) -> PaymentConfigResponse:
    """Create or update a payment platform config."""
    if platform not in _VALID_PLATFORMS:
        raise PaymentConfigInvalidError(
            user_message="這個金流平台不在支援清單內", context={"platform": platform}
        )

    repo = DonationRepository(pool, settings.payment_encryption_key or None)

    hash_key = body.hash_key
    hash_iv = body.hash_iv

    if platform in {"ecpay", "opay", "newebpay"} and not (hash_key and hash_iv):
        # Allow omitting keys on update if they're already stored.
        existing = await repo.get_config(user_id, platform)
        if not existing or not existing.hash_key or not existing.hash_iv:
            raise PaymentConfigInvalidError(
                user_message="這個金流平台需要填寫完整的金鑰資料",
                context={"platform": platform},
            )
        # Preserve existing decrypted values — repo will re-encrypt on write.
        hash_key = existing.hash_key
        hash_iv = existing.hash_iv

    config = await repo.upsert_config(
        user_id=user_id,
        platform=platform,
        merchant_id=body.merchant_id,
        hash_key=hash_key,
        hash_iv=hash_iv,
        min_amount=body.min_amount,
        media_share_enabled=body.media_share_enabled,
        enabled=body.enabled,
    )
    LOGGER.info("payment_config_upserted", extra={"platform": platform})
    return PaymentConfigResponse(
        platform=config.platform,
        merchant_id=config.merchant_id,
        has_hash=bool(config.hash_key),
        min_amount=config.min_amount,
        media_share_enabled=config.media_share_enabled,
        enabled=config.enabled,
        updated_at=config.updated_at,
    )


@router.delete("/{platform}")
async def delete_payment_config(
    platform: str,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
    _: None = Depends(require_activated),
) -> dict[str, str]:
    """Delete a payment platform config."""
    if platform not in _VALID_PLATFORMS:
        raise PaymentConfigInvalidError(
            user_message="這個金流平台不在支援清單內", context={"platform": platform}
        )

    repo = DonationRepository(pool)
    deleted = await repo.delete_config(user_id=user_id, platform=platform)
    if not deleted:
        raise PaymentConfigNotFoundError(context={"platform": platform})
    LOGGER.info("payment_config_deleted", extra={"platform": platform})
    return {"status": "ok"}
