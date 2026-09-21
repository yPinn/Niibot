"""Public donation endpoints: browse configs, checkout, and payment webhooks.

Payment flow:
  1. GET  /api/donate/public/{username}     → donor sees available platforms
  2. POST /api/donate/{username}/checkout   → backend builds a signed payment form
  3. Browser auto-submits to the gateway
  4. Gateway POSTs a webhook to /api/donate/webhook/{platform}
  5. Backend verifies, marks the order paid, optionally enqueues a video

Per-gateway signing/verification lives in ``services.payment``; this module owns
the order lifecycle and the HTTP surface.
"""

import logging
from urllib.parse import urlparse

from asyncpg import Pool
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import get_db_pool
from core.rate_limit import RateLimiter
from services.payment import CheckoutContext, WebhookResult, get_provider
from shared.errors import AppError, ChannelNotFoundError, InvalidInputError, NotFoundError
from shared.models.donation import DonationOrder, PaymentConfig
from shared.repositories.donation import DonationRepository, generate_trade_no
from shared.repositories.video_queue import (
    VideoQueueBlocklistRepository,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
)
from shared.services.video_queue_admission import AdmissionRejected, VideoQueueAdmissionService
from shared.video_sources import (
    extract_youtube_info,
    fetch_video_metadata,
    resolve_video_url,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/donate", tags=["donation"])

# 10 checkout attempts per minute per IP
_checkout_limiter = RateLimiter(max_calls=10, period=60.0)


class DonationInvalidError(InvalidInputError):
    code = "DONATION.INVALID"
    user_message = "贊助資料有誤，請檢查後再試"


class DonationTargetNotFoundError(NotFoundError):
    code = "DONATION.TARGET_NOT_FOUND"
    user_message = "找不到可用的贊助管道"


class DonationGatewayUnavailableError(AppError):
    code = "DONATION.GATEWAY_UNAVAILABLE"
    http_status = 503
    user_message = "這個頻道的贊助功能暫時無法使用"


def _extract_video_id(youtube_url: str | None, media_share_enabled: bool) -> str | None:
    """Validate and extract a YouTube video ID from a URL.

    Returns the video ID if valid and media share is enabled, else None.
    Raises DonationInvalidError if the URL is provided but invalid.
    """
    if not youtube_url or not media_share_enabled:
        return None
    video_id, _ = extract_youtube_info(youtube_url)
    if not video_id:
        raise DonationInvalidError(
            user_message="Donate 點播目前只支援 YouTube，請檢查影片網址",
            context={"field": "youtube_url"},
        )
    return video_id


async def _enqueue_donated_video(
    pool: Pool,
    channel_id: str,
    youtube_video_id: str,
    message: str | None,
    platform: str,
    trade_no: str,
    app_settings: Settings,
) -> None:
    """Admit paid media share without changing the already-settled payment."""
    try:
        vq_repo = VideoQueueRepository(pool)
        admission = VideoQueueAdmissionService(
            vq_repo,
            VideoQueueSettingsRepository(pool),
            VideoQueueBlocklistRepository(pool),
        )
        await admission.admit(
            channel_id=channel_id,
            url=f"https://youtu.be/{youtube_video_id}",
            requested_by=message or "斗內點播",
            source="donation",
            resolve=lambda url: resolve_video_url(url),
            fetch_metadata=lambda resolved: fetch_video_metadata(
                resolved,
                youtube_api_key=app_settings.youtube_api_key,
                twitch_client_id=app_settings.client_id,
                twitch_client_secret=app_settings.client_secret,
                instafix_host=app_settings.instafix_host,
            ),
        )
        LOGGER.info(
            f"[{platform} webhook] Enqueued video {youtube_video_id} for channel {channel_id}"
        )
    except AdmissionRejected as error:
        LOGGER.info(
            "[%s webhook] Paid video %s was not admitted: %s",
            platform,
            youtube_video_id,
            error.reason.value,
        )
    except Exception:
        # Enqueue is best-effort; the payment itself already succeeded.
        LOGGER.exception(f"[{platform} webhook] Failed to enqueue video for order {trade_no}")


class PublicPlatformInfo(BaseModel):
    platform: str
    min_amount: int
    media_share_enabled: bool


class PublicDonateInfo(BaseModel):
    username: str
    display_name: str | None = None
    platforms: list[PublicPlatformInfo]


class CheckoutRequest(BaseModel):
    platform: str
    amount: int = Field(..., ge=1, le=99999)
    message: str | None = Field(default=None, max_length=50)
    youtube_url: str | None = Field(default=None, max_length=200)
    return_url: str | None = None  # frontend success redirect (optional)


class CheckoutResponse(BaseModel):
    gateway_url: str
    form_params: dict[str, str]  # POST these to gateway_url


@router.get("/public/{username}", response_model=PublicDonateInfo)
async def get_public_donate_info(
    username: str,
    pool: Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
) -> PublicDonateInfo:
    """Return a streamer's enabled donation platforms (no secrets)."""
    repo = DonationRepository(pool, settings.payment_encryption_key or None)
    result = await repo.get_configs_by_username(username)
    if result is None:
        raise ChannelNotFoundError(context={"username": username})

    _user_id, _channel_id, configs = result
    return PublicDonateInfo(
        username=username,
        platforms=[
            PublicPlatformInfo(
                platform=c.platform,
                min_amount=c.min_amount,
                media_share_enabled=c.media_share_enabled,
            )
            for c in configs
            if c.enabled
        ],
    )


@router.post("/{username}/checkout", response_model=CheckoutResponse)
async def checkout(
    username: str,
    body: CheckoutRequest,
    request: Request,
    pool: Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Build a signed payment form for the chosen gateway.

    The frontend receives gateway_url + form_params and auto-submits a POST form.
    For PayPal, returns a bare redirect URL (no form, no order row).
    """
    _checkout_limiter.require(request.client.host if request.client else "unknown")

    provider = get_provider(body.platform)
    if provider is None:
        raise DonationInvalidError(
            user_message="這個贊助平台不在支援清單內", context={"platform": body.platform}
        )

    if body.return_url:
        _parsed = urlparse(body.return_url)
        _allowed = urlparse(settings.frontend_url)
        if _parsed.scheme != _allowed.scheme or _parsed.netloc != _allowed.netloc:
            raise DonationInvalidError(
                user_message="回傳網址無效", context={"return_url": body.return_url}
            )

    repo = DonationRepository(pool, settings.payment_encryption_key or None)
    result = await repo.get_configs_by_username(username)
    if result is None:
        raise ChannelNotFoundError(context={"username": username})

    user_id, channel_id, configs = result
    config = next((c for c in configs if c.platform == body.platform and c.enabled), None)
    if config is None:
        raise DonationTargetNotFoundError(context={"platform": body.platform})

    if body.amount < config.min_amount:
        raise DonationInvalidError(
            user_message="贊助金額低於這個頻道設定的最低金額",
            context={"amount": body.amount, "min_amount": config.min_amount},
        )

    # PayPal: bare redirect, no signed form, no order row.
    if provider.redirect_only:
        return CheckoutResponse(gateway_url=config.merchant_id, form_params={})

    if provider.needs_hash and not (config.hash_key and config.hash_iv):
        raise DonationGatewayUnavailableError(context={"platform": body.platform})

    youtube_video_id = _extract_video_id(body.youtube_url, config.media_share_enabled)
    trade_no = generate_trade_no()
    await repo.create_order(
        user_id=user_id,
        channel_id=channel_id,
        platform=body.platform,
        merchant_trade_no=trade_no,
        amount=body.amount,
        message=body.message,
        youtube_video_id=youtube_video_id,
    )

    ctx = CheckoutContext(
        merchant_id=config.merchant_id,
        hash_key=config.hash_key,
        hash_iv=config.hash_iv,
        trade_no=trade_no,
        amount=body.amount,
        item_name="斗內贊助",
        trade_desc="Niibot donation",
        message=body.message,
        youtube_video_id=youtube_video_id,
        notify_url=f"{settings.api_url}/api/donate/webhook/{body.platform}",
        client_back_url=body.return_url,
    )
    gateway_url, form_params = provider.build_checkout(ctx)
    return CheckoutResponse(gateway_url=gateway_url, form_params=form_params)


async def _apply_payment_result(
    repo: DonationRepository,
    pool: Pool,
    platform: str,
    config: PaymentConfig,
    result: WebhookResult,
    order: DonationOrder | None,
    app_settings: Settings,
) -> bool:
    """Advance the order per a verified webhook result. Returns True on ack-OK."""
    if order is None:
        order = await repo.get_order_by_trade_no(result.trade_no)
    if order is None:
        LOGGER.warning(f"[{platform} webhook] Unknown order: {result.trade_no}")
        return False

    if result.outcome == "failed":
        LOGGER.info(f"[{platform} webhook] Order {result.trade_no} failed/cancelled")
        await repo.mark_failed(result.trade_no)
        return True

    if result.outcome == "pending":
        # Reserved for the ATM/CVS two-stage flow (P2); no provider emits it yet.
        return True

    if result.paid_amount != int(order.amount):
        LOGGER.warning(
            f"[{platform} webhook] Amount mismatch for {result.trade_no}: "
            f"expected {order.amount}, got {result.paid_amount}"
        )
        return False

    paid_order = await repo.mark_paid(result.trade_no)
    if paid_order is None:
        return True  # already processed (duplicate webhook)

    LOGGER.info(
        f"[{platform} webhook] Order {result.trade_no} paid — "
        f"user={order.user_id} amount={order.amount}"
    )

    if paid_order.youtube_video_id and config.media_share_enabled and paid_order.channel_id:
        await _enqueue_donated_video(
            pool,
            paid_order.channel_id,
            paid_order.youtube_video_id,
            paid_order.message,
            platform,
            result.trade_no,
            app_settings,
        )

    return True


@router.post("/webhook/{platform}")
async def payment_webhook(
    platform: str,
    request: Request,
    pool: Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Gateway payment notification. Response format is provider-specific."""
    provider = get_provider(platform)
    if provider is None or provider.redirect_only:
        return PlainTextResponse("0|Error")

    form = await request.form()
    form_data = {k: str(v) for k, v in form.items()}
    repo = DonationRepository(pool, settings.payment_encryption_key or None)

    ref_kind, ref_val = provider.webhook_merchant_ref(form_data)
    order = None
    if ref_kind == "trade_no":
        order = await repo.get_order_by_trade_no(ref_val) if ref_val else None
        config = await repo.get_config(order.user_id, platform) if order else None
    else:
        config = await repo.get_config_by_merchant_id(platform, ref_val) if ref_val else None

    if config is None or not config.hash_key or not config.hash_iv:
        LOGGER.warning(f"[{platform} webhook] No usable config for incoming notification")
        return provider.webhook_ack(False)

    result = provider.verify_and_parse_webhook(form_data, config)
    if result is None:
        LOGGER.warning(f"[{platform} webhook] Signature/parse rejected")
        return provider.webhook_ack(False)

    ok = await _apply_payment_result(repo, pool, platform, config, result, order, settings)
    return provider.webhook_ack(ok)
