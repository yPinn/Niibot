"""Payment provider contract shared by every gateway integration.

A provider owns exactly three things: how to build a signed checkout form, how
to resolve which stored credential a webhook belongs to, and how to verify +
parse that webhook. Everything else (order lifecycle, video enqueue, rate
limiting) stays in the router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from fastapi import Response

from shared.models.donation import PaymentConfig

WebhookOutcome = Literal["paid", "failed", "pending"]

# ``pending`` is reserved for the ATM/CVS two-stage flow (P2) and is not
# produced by any provider yet — the router handles only paid/failed today.
MerchantRefKind = Literal["trade_no", "merchant_id"]


@dataclass(frozen=True)
class CheckoutContext:
    """Everything a provider needs to build one checkout form."""

    merchant_id: str
    hash_key: str | None
    hash_iv: str | None
    trade_no: str
    amount: int
    item_name: str
    trade_desc: str
    message: str | None
    youtube_video_id: str | None
    notify_url: str
    client_back_url: str | None


@dataclass(frozen=True)
class WebhookResult:
    """Verified outcome of a gateway webhook."""

    trade_no: str
    outcome: WebhookOutcome
    paid_amount: int | None
    gateway_trade_no: str | None  # the gateway's own trade id (kept for P3 reconciliation)
    raw: dict


class PaymentProvider(Protocol):
    """Structural contract — concrete providers just need matching attributes."""

    name: str
    needs_hash: bool
    redirect_only: bool  # True => no signed form, no webhook (PayPal)

    def gateway_url(self, *, sandbox: bool = False) -> str: ...

    def build_checkout(self, ctx: CheckoutContext) -> tuple[str, dict[str, str]]:
        """Return (gateway_url, form_params) for the browser to POST."""
        ...

    def webhook_merchant_ref(self, form: dict[str, str]) -> tuple[MerchantRefKind, str]:
        """How to look up the stored ``PaymentConfig`` for this webhook.

        ECPay/OPay carry ``MerchantTradeNo`` (order -> user -> config); NewebPay
        carries ``MerchantID`` directly.
        """
        ...

    def verify_and_parse_webhook(
        self, form: dict[str, str], config: PaymentConfig
    ) -> WebhookResult | None:
        """Verify the signature and parse the payload. ``None`` => reject."""
        ...

    def webhook_ack(self, ok: bool) -> Response:
        """The exact acknowledgement body/format this gateway expects."""
        ...


def coerce_int(raw: object) -> int | None:
    """Parse a gateway-reported amount; ``None`` if it is not a clean integer.

    Mirrors the old ``_amount_matches`` leniency: ``"200.50"`` and ``"abc"``
    both fail, so a mismatch is reported rather than a crash.
    """
    try:
        return int(raw)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
