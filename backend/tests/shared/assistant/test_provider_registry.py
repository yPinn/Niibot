"""Tests for explicit provider registration and capability settings."""

from __future__ import annotations

from shared.assistant.providers.registry import (
    ProviderConfig,
    ProviderKind,
    ProviderState,
    build_provider_registry,
)


def test_registry_preserves_explicit_speed_first_order() -> None:
    registry = build_provider_registry(
        {
            ProviderKind.GROQ: ProviderConfig("groq-secret", "openai/gpt-oss-120b"),
            ProviderKind.GEMINI: ProviderConfig("gemini-secret", "gemini-3.5-flash"),
            ProviderKind.OPENROUTER: ProviderConfig(
                "openrouter-secret", "inclusionai/ling-3.0-flash-vl:free"
            ),
        },
        provider_order=(
            ProviderKind.GROQ,
            ProviderKind.GEMINI,
            ProviderKind.OPENROUTER,
        ),
        timeout_seconds=8.0,
    )

    assert [spec.kind for spec in registry.specs] == [
        ProviderKind.GROQ,
        ProviderKind.GEMINI,
        ProviderKind.OPENROUTER,
    ]
    assert [spec.model for spec in registry.specs] == [
        "openai/gpt-oss-120b",
        "gemini-3.5-flash",
        "inclusionai/ling-3.0-flash-vl:free",
    ]


def test_registry_does_not_supply_implicit_model_defaults() -> None:
    registry = build_provider_registry(
        {ProviderKind.GROQ: ProviderConfig("groq-secret", "")},
        provider_order=(ProviderKind.GROQ,),
        timeout_seconds=8.0,
    )

    assert registry.specs == ()
    assert registry.registrations[0].state is ProviderState.MISCONFIGURED
    assert registry.registrations[0].reason == "missing_model"


def test_model_without_key_is_reported_as_misconfigured() -> None:
    registry = build_provider_registry(
        {ProviderKind.GEMINI: ProviderConfig("", "gemini-3.5-flash")},
        provider_order=(ProviderKind.GEMINI,),
        timeout_seconds=8.0,
    )

    assert registry.specs == ()
    assert registry.registrations[0].state is ProviderState.MISCONFIGURED
    assert registry.registrations[0].reason == "missing_key"


def test_empty_provider_config_is_disabled_not_misconfigured() -> None:
    registry = build_provider_registry(
        {ProviderKind.OPENROUTER: ProviderConfig()},
        provider_order=(ProviderKind.OPENROUTER,),
        timeout_seconds=8.0,
    )

    assert registry.registrations[0].state is ProviderState.DISABLED
    assert registry.registrations[0].reason is None


def test_provider_secrets_are_redacted_from_representations() -> None:
    secret = "never-print-this-secret"
    config = ProviderConfig(secret, "openai/gpt-oss-120b")
    registry = build_provider_registry(
        {ProviderKind.GROQ: config},
        provider_order=(ProviderKind.GROQ,),
        timeout_seconds=8.0,
    )

    assert secret not in repr(config)
    assert secret not in repr(registry.specs[0])
    assert secret not in repr(registry)


def test_provider_options_capture_qualified_reasoning_settings() -> None:
    registry = build_provider_registry(
        {
            ProviderKind.GROQ: ProviderConfig("key", "openai/gpt-oss-120b"),
            ProviderKind.GEMINI: ProviderConfig("key", "gemini-3.5-flash"),
            ProviderKind.OPENROUTER: ProviderConfig("key", "inclusionai/ling-3.0-flash-vl:free"),
        },
        provider_order=(
            ProviderKind.GROQ,
            ProviderKind.GEMINI,
            ProviderKind.OPENROUTER,
        ),
        timeout_seconds=8.0,
    )
    groq, gemini, openrouter = registry.specs

    assert groq.options.reasoning_effort == "low"
    assert groq.options.reasoning_format == "hidden"
    assert gemini.options.reasoning_effort == "minimal"
    assert openrouter.options.include_reasoning is False
    assert openrouter.options.disable_reasoning is True
    assert openrouter.options.require_zero_price is True
