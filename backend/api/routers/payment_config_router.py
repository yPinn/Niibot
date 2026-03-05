"""Payment config management endpoints (authenticated).

Streamers use these to store their ECPay/OPay/PayPal merchant credentials.
Credentials are stored server-side; hash_key/hash_iv are never returned raw.
"""

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_user_id, get_db_pool
from shared.repositories.donation import DonationRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment-configs", tags=["payment-configs"])

_VALID_PLATFORMS = {"ecpay", "opay", "paypal", "newebpay"}

# ============================================================
# Pydantic models
# ============================================================


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


# ============================================================
# Endpoints
# ============================================================


@router.get("", response_model=list[PaymentConfigResponse])
async def list_payment_configs(
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> list[PaymentConfigResponse]:
    """List all payment platform configs for the authenticated streamer."""
    try:
        repo = DonationRepository(pool)
        configs = await repo.list_configs(user_id)
        return [
            PaymentConfigResponse(
                platform=c.platform,
                merchant_id=c.merchant_id,
                has_hash=bool(c.hash_key),
                min_amount=c.min_amount,
                media_share_enabled=c.media_share_enabled,
                enabled=c.enabled,
                updated_at=c.updated_at,
            )
            for c in configs
        ]
    except Exception:
        logger.exception("Failed to list payment configs for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch payment configs") from None


@router.put("/{platform}", response_model=PaymentConfigResponse)
async def upsert_payment_config(
    platform: str,
    body: PaymentConfigUpsert,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> PaymentConfigResponse:
    """Create or update a payment platform config."""
    if platform not in _VALID_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform. Must be one of: {', '.join(sorted(_VALID_PLATFORMS))}",
        )

    # ECPay/OPay/NewebPay require hash_key and hash_iv
    if platform in {"ecpay", "opay", "newebpay"} and not (body.hash_key and body.hash_iv):
        raise HTTPException(status_code=400, detail=f"{platform} requires hash_key and hash_iv")

    try:
        repo = DonationRepository(pool)
        config = await repo.upsert_config(
            user_id=user_id,
            platform=platform,
            merchant_id=body.merchant_id,
            hash_key=body.hash_key,
            hash_iv=body.hash_iv,
            min_amount=body.min_amount,
            media_share_enabled=body.media_share_enabled,
            enabled=body.enabled,
        )
        logger.info("User %s upserted payment config for platform %s", user_id, platform)
        return PaymentConfigResponse(
            platform=config.platform,
            merchant_id=config.merchant_id,
            has_hash=bool(config.hash_key),
            min_amount=config.min_amount,
            media_share_enabled=config.media_share_enabled,
            enabled=config.enabled,
            updated_at=config.updated_at,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to upsert payment config for user %s platform %s", user_id, platform
        )
        raise HTTPException(status_code=500, detail="Failed to save payment config") from None


@router.delete("/{platform}")
async def delete_payment_config(
    platform: str,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> dict[str, str]:
    """Delete a payment platform config."""
    if platform not in _VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail="Invalid platform")

    try:
        repo = DonationRepository(pool)
        deleted = await repo.delete_config(user_id=user_id, platform=platform)
        if not deleted:
            raise HTTPException(status_code=404, detail="Config not found")
        logger.info("User %s deleted payment config for platform %s", user_id, platform)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to delete payment config for user %s platform %s", user_id, platform
        )
        raise HTTPException(status_code=500, detail="Failed to delete payment config") from None
