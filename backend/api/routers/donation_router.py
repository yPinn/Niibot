"""Public donation endpoints: browse configs, checkout, and payment webhooks.

Payment flow (ECPay / OPay — identical API):
  1. GET  /api/donate/public/{username}          → donor sees available platforms
  2. POST /api/donate/{username}/checkout        → backend builds signed payment form
  3. Browser auto-submits to ECPay/OPay gateway
  4. Gateway POSTs webhook to /api/donate/webhook/{platform}
  5. Backend verifies, marks order paid, optionally enqueues YouTube video
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from asyncpg import Pool
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import get_db_pool
from shared.repositories.donation import DonationRepository, generate_trade_no
from shared.repositories.video_queue import VideoQueueRepository, extract_youtube_info

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/donate", tags=["donation"])


def _extract_video_id(youtube_url: str | None, media_share_enabled: bool) -> str | None:
    """Validate and extract YouTube video ID from a URL.

    Returns the video ID if valid and media share is enabled, else None.
    Raises HTTPException(400) if the URL is provided but invalid.
    """
    if not youtube_url or not media_share_enabled:
        return None
    video_id, _ = extract_youtube_info(youtube_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    return video_id


async def _enqueue_donated_video(
    pool: Pool,
    channel_id: str,
    youtube_video_id: str,
    message: str | None,
    platform: str,
    trade_no: str,
) -> None:
    """Enqueue a donated YouTube video. Errors are logged but do not fail the webhook."""
    try:
        vq_repo = VideoQueueRepository(pool)
        await vq_repo.add(
            channel_id=channel_id,
            video_id=youtube_video_id,
            requested_by=message or "斗內點播",
            source="donation",
        )
        LOGGER.info(
            f"[{platform} webhook] Enqueued video {youtube_video_id} for channel {channel_id}"
        )
    except Exception:
        LOGGER.exception(f"[{platform} webhook] Failed to enqueue video for order {trade_no}")


_GATEWAYS: dict[str, str] = {
    "ecpay": "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5",
    "opay": "https://payment.opay.tw/Cashier/AioCheckOut/V5",
    "newebpay": "https://core.newebpay.com/MPG/mpg_gateway",
}


def _build_check_mac_value(params: dict, hash_key: str, hash_iv: str) -> str:
    """Compute ECPay/OPay CheckMacValue.

    Algorithm:
      1. Remove CheckMacValue from params (if present)
      2. Sort remaining params alphabetically (case-insensitive)
      3. Build: HashKey={key}&{sorted_k=v...}&HashIV={iv}
      4. URL-encode (quote_plus, safe='-_.!()*'), then lowercase
      5. SHA-256 → UPPERCASE hex
    """
    filtered = {k: v for k, v in params.items() if k != "CheckMacValue"}
    sorted_pairs = sorted(filtered.items(), key=lambda x: x[0].lower())
    raw = (
        f"HashKey={hash_key}&"
        + "&".join(f"{k}={v}" for k, v in sorted_pairs)
        + f"&HashIV={hash_iv}"
    )
    encoded = urllib.parse.quote_plus(raw, safe="-_.!()*").lower()
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def _verify_webhook_mac(form_data: dict, hash_key: str, hash_iv: str) -> bool:
    received = form_data.get("CheckMacValue", "")
    computed = _build_check_mac_value(form_data, hash_key, hash_iv)
    return hmac.compare_digest(received.upper(), computed)


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("Empty data cannot be unpadded")
    pad_len = data[-1]
    if pad_len == 0 or pad_len > 16:
        raise ValueError(f"Invalid PKCS7 padding length: {pad_len}")
    if len(data) < pad_len:
        raise ValueError("Data shorter than padding length")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid PKCS7 padding bytes")
    return data[:-pad_len]


def _newebpay_aes_encrypt(plaintext: str, hash_key: str, hash_iv: str) -> str:
    """AES-256-CBC encrypt → lowercase hex (NewebPay TradeInfo)."""
    key = hash_key.encode("utf-8")
    iv = hash_iv.encode("utf-8")
    padded = _pkcs7_pad(plaintext.encode("utf-8"))
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    return (enc.update(padded) + enc.finalize()).hex()


def _newebpay_aes_decrypt(hex_data: str, hash_key: str, hash_iv: str) -> str:
    """AES-256-CBC decrypt from lowercase hex (NewebPay webhook TradeInfo)."""
    key = hash_key.encode("utf-8")
    iv = hash_iv.encode("utf-8")
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(bytes.fromhex(hex_data)) + dec.finalize()
    return _pkcs7_unpad(padded).decode("utf-8")


def _newebpay_sha256(trade_info_hex: str, hash_key: str, hash_iv: str) -> str:
    """SHA-256 of HashKey={key}&{trade_info}&HashIV={iv} → UPPERCASE hex."""
    raw = f"HashKey={hash_key}&{trade_info_hex}&HashIV={hash_iv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _build_newebpay_trade_info(
    merchant_id: str,
    order_no: str,
    amount: int,
    notify_url: str,
    return_url: str | None,
    message: str | None,
) -> str:
    """Build URL-encoded TradeInfo string (before AES encryption)."""
    params: dict[str, str] = {
        "MerchantID": merchant_id,
        "RespondType": "JSON",
        "TimeStamp": str(int(time.time())),
        "Version": "2.0",
        "MerchantOrderNo": order_no,
        "Amt": str(amount),
        "ItemDesc": (message or "Niibot 斗內贊助")[:50],
        "NotifyURL": notify_url,
        "LoginType": "0",
    }
    if return_url:
        params["ReturnURL"] = return_url
    return urllib.parse.urlencode(params)


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
) -> PublicDonateInfo:
    """Return a streamer's enabled donation platforms (no secrets)."""
    repo = DonationRepository(pool)
    result = await repo.get_configs_by_username(username)
    if result is None:
        raise HTTPException(status_code=404, detail="Streamer not found")

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
    pool: Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Build a signed payment form for ECPay / OPay.

    The frontend receives gateway_url + form_params and auto-submits a POST form.
    For PayPal, returns a simple redirect (no form signing needed).
    """
    if body.platform not in _GATEWAYS and body.platform != "paypal":
        raise HTTPException(status_code=400, detail="Unsupported platform")

    if body.return_url:
        _parsed = urlparse(body.return_url)
        _allowed = urlparse(settings.frontend_url)
        if _parsed.scheme != _allowed.scheme or _parsed.netloc != _allowed.netloc:
            raise HTTPException(status_code=400, detail="Invalid return_url")

    repo = DonationRepository(pool)
    result = await repo.get_configs_by_username(username)
    if result is None:
        raise HTTPException(status_code=404, detail="Streamer not found")

    user_id, channel_id, configs = result
    config = next((c for c in configs if c.platform == body.platform and c.enabled), None)
    if config is None:
        raise HTTPException(status_code=404, detail="Platform not configured or disabled")

    if body.amount < config.min_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum donation amount is NT${config.min_amount}",
        )

    # ------------------------------------------------------------------
    # PayPal: simple redirect, no backend signing
    # ------------------------------------------------------------------
    if body.platform == "paypal":
        return CheckoutResponse(
            gateway_url=config.merchant_id,  # stored as paypal.me URL
            form_params={},
        )

    # ------------------------------------------------------------------
    # NewebPay: AES-encrypted TradeInfo form
    # ------------------------------------------------------------------
    if body.platform == "newebpay":
        if not config.hash_key or not config.hash_iv:
            raise HTTPException(status_code=500, detail="Payment gateway not configured")

        youtube_video_id_nb = _extract_video_id(body.youtube_url, config.media_share_enabled)

        trade_no = generate_trade_no()
        await repo.create_order(
            user_id=user_id,
            channel_id=channel_id,
            platform=body.platform,
            merchant_trade_no=trade_no,
            amount=body.amount,
            message=body.message,
            youtube_video_id=youtube_video_id_nb,
        )

        notify_url = f"{settings.api_url}/api/donate/webhook/newebpay"

        trade_info_str = _build_newebpay_trade_info(
            merchant_id=config.merchant_id,
            order_no=trade_no,
            amount=body.amount,
            notify_url=notify_url,
            return_url=body.return_url,
            message=body.message,
        )
        trade_info_hex = _newebpay_aes_encrypt(trade_info_str, config.hash_key, config.hash_iv)
        trade_sha = _newebpay_sha256(trade_info_hex, config.hash_key, config.hash_iv)

        nb_params: dict[str, str] = {
            "MerchantID": config.merchant_id,
            "TradeInfo": trade_info_hex,
            "TradeSha": trade_sha,
            "Version": "2.0",
        }
        return CheckoutResponse(gateway_url=_GATEWAYS["newebpay"], form_params=nb_params)

    # ------------------------------------------------------------------
    # ECPay / OPay: generate signed payment form
    # ------------------------------------------------------------------
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

    notify_url = f"{settings.api_url}/api/donate/webhook/{body.platform}"

    trade_date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M:%S")

    params: dict[str, str] = {
        "MerchantID": config.merchant_id,
        "MerchantTradeNo": trade_no,
        "MerchantTradeDate": trade_date,
        "PaymentType": "aio",
        "TotalAmount": str(body.amount),
        "TradeDesc": "Niibot donation",
        "ItemName": "斗內贊助",
        "ReturnURL": notify_url,
        "ChoosePayment": "ALL",
        "EncryptType": "1",
    }

    # ECPay/OPay spec limits CustomField1/2 to 50 chars each
    if youtube_video_id:
        params["CustomField1"] = youtube_video_id
    if body.message:
        params["CustomField2"] = body.message[:50]

    if body.return_url:
        params["ClientBackURL"] = body.return_url

    if not config.hash_key or not config.hash_iv:
        raise HTTPException(status_code=500, detail="Payment gateway not configured")
    params["CheckMacValue"] = _build_check_mac_value(params, config.hash_key, config.hash_iv)

    gateway_url = _GATEWAYS[body.platform]
    return CheckoutResponse(gateway_url=gateway_url, form_params=params)


async def _handle_payment_webhook(
    platform: str,
    form_data: dict[str, str],
    pool: Pool,
) -> str:
    """Shared webhook handler for ECPay and OPay (identical protocol).

    Returns "1|OK" on success, "0|Error" on failure.
    ECPay/OPay will retry if response is not exactly "1|OK".
    """
    trade_no = form_data.get("MerchantTradeNo")
    rtn_code = form_data.get("RtnCode")

    if not trade_no:
        LOGGER.warning(f"[{platform} webhook] Missing MerchantTradeNo")
        return "0|Error"

    repo = DonationRepository(pool)
    order = await repo.get_order_by_trade_no(trade_no)
    if order is None:
        LOGGER.warning(f"[{platform} webhook] Unknown order: {trade_no}")
        return "0|Error"

    # Look up the streamer's hash to verify the webhook signature
    config = await repo.get_config(order.user_id, platform)
    if config is None:
        LOGGER.error(f"[{platform} webhook] No config found for user {order.user_id}")
        return "0|Error"

    if not config.hash_key or not config.hash_iv:
        LOGGER.error(
            f"[{platform} webhook] hash_key/hash_iv not configured for user {order.user_id}"
        )
        return "0|Error"
    if not _verify_webhook_mac(form_data, config.hash_key, config.hash_iv):
        LOGGER.warning(f"[{platform} webhook] CheckMacValue mismatch for order {trade_no}")
        return "0|Error"

    if rtn_code != "1":
        LOGGER.info(f"[{platform} webhook] Order {trade_no} failed/cancelled, RtnCode={rtn_code}")
        await repo.mark_failed(trade_no)
        return "1|OK"

    trade_amt = form_data.get("TradeAmt")
    try:
        webhook_amount = int(trade_amt) if trade_amt is not None else None
    except ValueError:
        webhook_amount = None
    if webhook_amount is None or webhook_amount != int(order.amount):
        LOGGER.warning(
            f"[{platform} webhook] Amount mismatch for {trade_no}: "
            f"expected {order.amount}, got {trade_amt}"
        )
        return "0|Error"

    # Mark order as paid
    paid_order = await repo.mark_paid(trade_no)
    if paid_order is None:
        # Already processed (duplicate webhook)
        return "1|OK"

    LOGGER.info(
        f"[{platform} webhook] Order {trade_no} paid — user={order.user_id} amount={order.amount}"
    )

    # Enqueue YouTube video if media share is enabled
    if paid_order.youtube_video_id and config.media_share_enabled and paid_order.channel_id:
        await _enqueue_donated_video(
            pool,
            paid_order.channel_id,
            paid_order.youtube_video_id,
            paid_order.message,
            platform,
            trade_no,
        )

    return "1|OK"


@router.post("/webhook/ecpay", response_class=PlainTextResponse)
async def webhook_ecpay(
    request: Request,
    pool: Pool = Depends(get_db_pool),
) -> str:
    """ECPay payment notification webhook."""
    form = await request.form()
    form_data = {k: str(v) for k, v in form.items()}
    return await _handle_payment_webhook("ecpay", form_data, pool)


@router.post("/webhook/opay", response_class=PlainTextResponse)
async def webhook_opay(
    request: Request,
    pool: Pool = Depends(get_db_pool),
) -> str:
    """OPay payment notification webhook."""
    form = await request.form()
    form_data = {k: str(v) for k, v in form.items()}
    return await _handle_payment_webhook("opay", form_data, pool)


@router.post("/webhook/newebpay")
async def webhook_newebpay(
    request: Request,
    pool: Pool = Depends(get_db_pool),
) -> JSONResponse:
    """NewebPay payment notification webhook.

    NewebPay POSTs form data with:
      Status     — "SUCCESS" or error string
      MerchantID — merchant ID
      TradeInfo  — AES-256-CBC encrypted hex of JSON trade result
      TradeSha   — SHA-256 verification hash
      Version    — "2.0"

    Response must be HTTP 200 (NewebPay ignores body).
    """
    form = await request.form()
    status = str(form.get("Status", ""))
    trade_info_hex = str(form.get("TradeInfo", ""))
    trade_sha = str(form.get("TradeSha", ""))

    if not trade_info_hex or not trade_sha:
        LOGGER.warning("[newebpay webhook] Missing TradeInfo or TradeSha")
        return JSONResponse({"status": "error"}, status_code=200)

    # Resolve the merchant's credentials from MerchantID in the raw form
    # (we need to look up the user by merchant_id to get hash_key/hash_iv)
    merchant_id = str(form.get("MerchantID", ""))
    repo = DonationRepository(pool)
    config_row = await repo.get_config_by_merchant_id("newebpay", merchant_id)
    if config_row is None:
        LOGGER.warning(f"[newebpay webhook] Unknown merchant_id: {merchant_id}")
        return JSONResponse({"status": "error"}, status_code=200)

    if not config_row.hash_key or not config_row.hash_iv:
        LOGGER.error(
            f"[newebpay webhook] hash_key/hash_iv not configured for merchant {merchant_id}"
        )
        return JSONResponse({"status": "error"}, status_code=200)

    # Verify TradeSha
    expected_sha = _newebpay_sha256(trade_info_hex, config_row.hash_key, config_row.hash_iv)
    if not hmac.compare_digest(trade_sha.upper(), expected_sha):
        LOGGER.warning(f"[newebpay webhook] TradeSha mismatch for merchant {merchant_id}")
        return JSONResponse({"status": "error"}, status_code=200)

    # Decrypt TradeInfo
    try:
        trade_json = _newebpay_aes_decrypt(trade_info_hex, config_row.hash_key, config_row.hash_iv)
        trade_data = json.loads(trade_json)
    except Exception:
        LOGGER.exception("[newebpay webhook] Failed to decrypt TradeInfo")
        return JSONResponse({"status": "error"}, status_code=200)

    inner_status = trade_data.get("Status", "")
    trade_no = trade_data.get("MerchantOrderNo", "")

    if not trade_no:
        LOGGER.warning("[newebpay webhook] Missing MerchantOrderNo in decrypted data")
        return JSONResponse({"status": "error"}, status_code=200)

    order = await repo.get_order_by_trade_no(trade_no)
    if order is None:
        LOGGER.warning(f"[newebpay webhook] Unknown order: {trade_no}")
        return JSONResponse({"status": "error"}, status_code=200)

    if inner_status != "SUCCESS" or status != "SUCCESS":
        LOGGER.info(f"[newebpay webhook] Order {trade_no} failed, Status={inner_status}")
        await repo.mark_failed(trade_no)
        return JSONResponse({"status": "ok"}, status_code=200)

    paid_order = await repo.mark_paid(trade_no)
    if paid_order is None:
        return JSONResponse({"status": "ok"}, status_code=200)  # duplicate webhook

    LOGGER.info(
        f"[newebpay webhook] Order {trade_no} paid — user={order.user_id} amount={order.amount}"
    )

    if paid_order.youtube_video_id and config_row.media_share_enabled and paid_order.channel_id:
        await _enqueue_donated_video(
            pool,
            paid_order.channel_id,
            paid_order.youtube_video_id,
            paid_order.message,
            "newebpay",
            trade_no,
        )

    return JSONResponse({"status": "ok"}, status_code=200)
