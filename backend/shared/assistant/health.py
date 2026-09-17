"""Secret-safe helpers for exposing assistant runtime health."""

from __future__ import annotations

from collections.abc import Mapping


def primary_model_label(status: object) -> str | None:
    """Return the first ready provider/model label from a health payload."""

    if not isinstance(status, Mapping):
        return None

    providers = status.get("providers")
    if not isinstance(providers, (list, tuple)):
        return None

    for registration in providers:
        if not isinstance(registration, Mapping):
            continue
        if registration.get("state") != "ready":
            continue

        provider = registration.get("provider")
        model = registration.get("model")
        if isinstance(provider, str) and provider and isinstance(model, str) and model:
            return f"{provider}/{model}"

    return None
