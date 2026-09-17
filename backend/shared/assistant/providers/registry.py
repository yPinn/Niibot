"""Explicit provider configuration and secret-safe registration state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from shared.assistant.contracts import MessageRole


class ProviderKind(StrEnum):
    GROQ = "groq"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class ProviderState(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    MISCONFIGURED = "misconfigured"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Raw environment-backed values with the credential redacted from repr."""

    api_key: str = field(default="", repr=False, compare=False)
    model: str = ""


@dataclass(frozen=True, slots=True)
class ProviderOptions:
    """Qualified request options for one provider/model combination."""

    temperature: float = 0.2
    reasoning_effort: str | None = None
    reasoning_format: str | None = None
    include_reasoning: bool | None = None
    disable_reasoning: bool = False
    require_zero_price: bool = False
    developer_role: MessageRole = MessageRole.SYSTEM


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Complete provider definition used to construct an adapter."""

    kind: ProviderKind
    model: str
    base_url: str
    api_key: str = field(repr=False, compare=False)
    timeout_seconds: float
    options: ProviderOptions

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("provider model must not be blank")
        if not self.api_key:
            raise ValueError("provider api_key must not be blank")
        if self.timeout_seconds <= 0:
            raise ValueError("provider timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    """Credential-free health information for one configured provider slot."""

    kind: ProviderKind
    state: ProviderState
    model: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    """Ordered ready specs plus health records for every requested provider."""

    specs: tuple[ProviderSpec, ...]
    registrations: tuple[ProviderRegistration, ...]


_BASE_URLS: dict[ProviderKind, str] = {
    ProviderKind.GROQ: "https://api.groq.com/openai/v1",
    ProviderKind.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai/",
    ProviderKind.OPENROUTER: "https://openrouter.ai/api/v1",
}


def _options_for(kind: ProviderKind, model: str) -> ProviderOptions:
    if kind is ProviderKind.GROQ and model.startswith("openai/gpt-oss-"):
        return ProviderOptions(reasoning_effort="low", reasoning_format="hidden")
    if kind is ProviderKind.GEMINI and model.startswith("gemini-3"):
        return ProviderOptions(reasoning_effort="minimal")
    if kind is ProviderKind.OPENROUTER:
        return ProviderOptions(
            include_reasoning=False,
            disable_reasoning=True,
            require_zero_price=True,
        )
    return ProviderOptions()


def build_provider_registry(
    configs: Mapping[ProviderKind, ProviderConfig],
    *,
    provider_order: tuple[ProviderKind, ...],
    timeout_seconds: float,
) -> ProviderRegistry:
    """Build a fixed ordered registry without implicit model defaults."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if len(set(provider_order)) != len(provider_order):
        raise ValueError("provider_order must not contain duplicates")

    specs: list[ProviderSpec] = []
    registrations: list[ProviderRegistration] = []

    for kind in provider_order:
        config = configs.get(kind, ProviderConfig())
        api_key = config.api_key.strip()
        model = config.model.strip()

        if not api_key and not model:
            registrations.append(ProviderRegistration(kind, ProviderState.DISABLED))
            continue
        if not api_key:
            registrations.append(
                ProviderRegistration(
                    kind,
                    ProviderState.MISCONFIGURED,
                    model=model,
                    reason="missing_key",
                )
            )
            continue
        if not model:
            registrations.append(
                ProviderRegistration(
                    kind,
                    ProviderState.MISCONFIGURED,
                    reason="missing_model",
                )
            )
            continue

        spec = ProviderSpec(
            kind=kind,
            model=model,
            base_url=_BASE_URLS[kind],
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            options=_options_for(kind, model),
        )
        specs.append(spec)
        registrations.append(ProviderRegistration(kind, ProviderState.READY, model=model))

    return ProviderRegistry(tuple(specs), tuple(registrations))
