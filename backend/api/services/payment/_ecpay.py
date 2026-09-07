"""ECPay AIO (and OPay, which speaks the identical protocol).

CMV-SHA256: the browser POSTs a signed form to the cashier; the gateway POSTs a
form-encoded webhook back to ``ReturnURL`` and expects a plain ``1|OK``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Response
from fastapi.responses import PlainTextResponse

from shared.models.donation import PaymentConfig

from ._base import CheckoutContext, MerchantRefKind, WebhookResult, coerce_int
from ._cmv import build_check_mac_value, verify_check_mac_value

_TAIPEI = timezone(timedelta(hours=8))


class EcpayProvider:
    name = "ecpay"
    needs_hash = True
    redirect_only = False

    _GATEWAY_PROD = "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5"
    _GATEWAY_STAGE = "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"

    def gateway_url(self, *, sandbox: bool = False) -> str:
        return self._GATEWAY_STAGE if sandbox else self._GATEWAY_PROD

    def build_checkout(self, ctx: CheckoutContext) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {
            "MerchantID": ctx.merchant_id,
            "MerchantTradeNo": ctx.trade_no,
            "MerchantTradeDate": datetime.now(_TAIPEI).strftime("%Y/%m/%d %H:%M:%S"),
            "PaymentType": "aio",
            "TotalAmount": str(ctx.amount),
            "TradeDesc": ctx.trade_desc,
            "ItemName": ctx.item_name,
            "ReturnURL": ctx.notify_url,
            "ChoosePayment": "ALL",
            "EncryptType": "1",
        }
        # ECPay/OPay spec limits CustomField1/2 to 50 chars each.
        if ctx.youtube_video_id:
            params["CustomField1"] = ctx.youtube_video_id
        if ctx.message:
            params["CustomField2"] = ctx.message[:50]
        if ctx.client_back_url:
            params["ClientBackURL"] = ctx.client_back_url

        assert ctx.hash_key and ctx.hash_iv  # guaranteed by the router
        params["CheckMacValue"] = build_check_mac_value(params, ctx.hash_key, ctx.hash_iv)
        return self.gateway_url(), params

    def webhook_merchant_ref(self, form: dict[str, str]) -> tuple[MerchantRefKind, str]:
        return "trade_no", form.get("MerchantTradeNo", "")

    def verify_and_parse_webhook(
        self, form: dict[str, str], config: PaymentConfig
    ) -> WebhookResult | None:
        if not config.hash_key or not config.hash_iv:
            return None
        if not verify_check_mac_value(form, config.hash_key, config.hash_iv):
            return None
        return WebhookResult(
            trade_no=form.get("MerchantTradeNo", ""),
            outcome="paid" if form.get("RtnCode") == "1" else "failed",
            paid_amount=coerce_int(form.get("TradeAmt")),
            gateway_trade_no=form.get("TradeNo") or None,
            raw=form,
        )

    def webhook_ack(self, ok: bool) -> Response:
        return PlainTextResponse("1|OK" if ok else "0|Error")


class OpayProvider(EcpayProvider):
    name = "opay"

    _GATEWAY_PROD = "https://payment.opay.tw/Cashier/AioCheckOut/V5"
    _GATEWAY_STAGE = "https://payment-stage.opay.tw/Cashier/AioCheckOut/V5"
