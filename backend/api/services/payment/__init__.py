"""Payment gateway providers.

Each provider owns its checkout-form signing and webhook verification; the
router owns the order lifecycle. Add a gateway by writing a ``_<name>.py``
module and registering it in ``PROVIDERS``.
"""

from ._base import (
    CheckoutContext,
    PaymentProvider,
    WebhookOutcome,
    WebhookResult,
    coerce_int,
)
from ._ecpay import EcpayProvider, OpayProvider
from ._newebpay import NewebpayProvider
from ._paypal import PaypalProvider

PROVIDERS: dict[str, PaymentProvider] = {
    "ecpay": EcpayProvider(),
    "opay": OpayProvider(),
    "newebpay": NewebpayProvider(),
    "paypal": PaypalProvider(),
}


def get_provider(name: str) -> PaymentProvider | None:
    """Look up a provider by platform key, or ``None`` if unsupported."""
    return PROVIDERS.get(name)


__all__ = [
    "PROVIDERS",
    "CheckoutContext",
    "EcpayProvider",
    "NewebpayProvider",
    "OpayProvider",
    "PaymentProvider",
    "PaypalProvider",
    "WebhookOutcome",
    "WebhookResult",
    "coerce_int",
    "get_provider",
]
