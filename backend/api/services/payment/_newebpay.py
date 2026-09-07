"""NewebPay (藍新金流) MPG gateway.

AES-JSON: the browser POSTs an AES-encrypted ``TradeInfo`` blob; the gateway
POSTs an AES-encrypted webhook and only cares that the response is HTTP 200.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
import urllib.parse

from fastapi import Response
from fastapi.responses import JSONResponse

from shared.models.donation import PaymentConfig

from ._base import CheckoutContext, MerchantRefKind, WebhookResult, coerce_int
from ._mpg import aes_decrypt, aes_encrypt, trade_sha256

LOGGER: logging.Logger = logging.getLogger(__name__)


def build_trade_info(
    *,
    merchant_id: str,
    order_no: str,
    amount: int,
    notify_url: str,
    return_url: str | None,
    message: str | None,
) -> str:
    """URL-encoded TradeInfo string (before AES encryption)."""
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


class NewebpayProvider:
    name = "newebpay"
    needs_hash = True
    redirect_only = False

    _GATEWAY_PROD = "https://core.newebpay.com/MPG/mpg_gateway"
    _GATEWAY_STAGE = "https://ccore.newebpay.com/MPG/mpg_gateway"

    def gateway_url(self, *, sandbox: bool = False) -> str:
        return self._GATEWAY_STAGE if sandbox else self._GATEWAY_PROD

    def build_checkout(self, ctx: CheckoutContext) -> tuple[str, dict[str, str]]:
        assert ctx.hash_key and ctx.hash_iv  # guaranteed by the router
        trade_info_str = build_trade_info(
            merchant_id=ctx.merchant_id,
            order_no=ctx.trade_no,
            amount=ctx.amount,
            notify_url=ctx.notify_url,
            return_url=ctx.client_back_url,
            message=ctx.message,
        )
        trade_info_hex = aes_encrypt(trade_info_str, ctx.hash_key, ctx.hash_iv)
        params = {
            "MerchantID": ctx.merchant_id,
            "TradeInfo": trade_info_hex,
            "TradeSha": trade_sha256(trade_info_hex, ctx.hash_key, ctx.hash_iv),
            "Version": "2.0",
        }
        return self.gateway_url(), params

    def webhook_merchant_ref(self, form: dict[str, str]) -> tuple[MerchantRefKind, str]:
        return "merchant_id", form.get("MerchantID", "")

    def verify_and_parse_webhook(
        self, form: dict[str, str], config: PaymentConfig
    ) -> WebhookResult | None:
        trade_info_hex = form.get("TradeInfo", "")
        trade_sha = form.get("TradeSha", "")
        if not trade_info_hex or not trade_sha:
            LOGGER.warning("[newebpay webhook] Missing TradeInfo or TradeSha")
            return None
        if not config.hash_key or not config.hash_iv:
            return None

        expected = trade_sha256(trade_info_hex, config.hash_key, config.hash_iv)
        if not hmac.compare_digest(trade_sha.upper(), expected):
            LOGGER.warning(
                "[newebpay webhook] TradeSha mismatch for merchant %s", form.get("MerchantID")
            )
            return None

        try:
            trade_data = json.loads(aes_decrypt(trade_info_hex, config.hash_key, config.hash_iv))
        except Exception:
            LOGGER.exception("[newebpay webhook] Failed to decrypt TradeInfo")
            return None

        trade_no = trade_data.get("MerchantOrderNo", "")
        if not trade_no:
            LOGGER.warning("[newebpay webhook] Missing MerchantOrderNo in decrypted data")
            return None

        succeeded = trade_data.get("Status") == "SUCCESS" and form.get("Status") == "SUCCESS"
        return WebhookResult(
            trade_no=trade_no,
            outcome="paid" if succeeded else "failed",
            paid_amount=coerce_int(trade_data.get("Amt")),
            gateway_trade_no=trade_data.get("TradeNo") or None,
            raw=trade_data,
        )

    def webhook_ack(self, ok: bool) -> Response:
        return JSONResponse({"status": "ok" if ok else "error"}, status_code=200)
