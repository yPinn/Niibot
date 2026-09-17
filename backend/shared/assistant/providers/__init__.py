"""Provider registry and adapters for the assistant harness."""

from shared.assistant.providers.openai_compatible import OpenAICompatibleProvider
from shared.assistant.providers.registry import (
    ProviderConfig,
    ProviderKind,
    ProviderOptions,
    ProviderRegistration,
    ProviderRegistry,
    ProviderSpec,
    ProviderState,
    build_provider_registry,
)

__all__ = [
    "OpenAICompatibleProvider",
    "ProviderConfig",
    "ProviderKind",
    "ProviderOptions",
    "ProviderRegistry",
    "ProviderRegistration",
    "ProviderSpec",
    "ProviderState",
    "build_provider_registry",
]
