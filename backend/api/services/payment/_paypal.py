"""PayPal — not a gateway integration, just a redirect to a stored paypal.me URL.

No signed form, no webhook, and (matching current behaviour) no local order row.
"""

from __future__ import annotations

from fastapi import Response
from fastapi.responses import PlainTextResponse

from shared.models.donation import PaymentConfig

from ._base import CheckoutContext, MerchantRefKind, WebhookResult


class PaypalProvider:
    name = "paypal"
    needs_hash = False
    redirect_only = True

    def gateway_url(self, *, sandbox: bool = False) -> str:
        raise NotImplementedError("PayPal has no fixed gateway URL — the merchant_id is the URL")

    def build_checkout(self, ctx: CheckoutContext) -> tuple[str, dict[str, str]]:
        return ctx.merchant_id, {}

    def webhook_merchant_ref(self, form: dict[str, str]) -> tuple[MerchantRefKind, str]:
        return "merchant_id", ""

    def verify_and_parse_webhook(
        self, form: dict[str, str], config: PaymentConfig
    ) -> WebhookResult | None:
        return None

    def webhook_ack(self, ok: bool) -> Response:
        return PlainTextResponse("0|Error")
