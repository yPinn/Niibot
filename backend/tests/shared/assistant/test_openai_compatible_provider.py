"""Tests for the OpenAI-compatible provider adapter with an injected fake client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from shared.assistant.contracts import (
    FailureKind,
    MessageRole,
    ProviderCompletion,
    ProviderFailure,
    ProviderMessage,
    ProviderRequest,
)
from shared.assistant.providers.openai_compatible import OpenAICompatibleProvider
from shared.assistant.providers.registry import (
    ProviderConfig,
    ProviderKind,
    build_provider_registry,
)


def _spec(kind: ProviderKind = ProviderKind.GROQ):
    models = {
        ProviderKind.GROQ: "openai/gpt-oss-120b",
        ProviderKind.GEMINI: "gemini-3.5-flash",
        ProviderKind.OPENROUTER: "inclusionai/ling-3.0-flash-vl:free",
    }
    registry = build_provider_registry(
        {kind: ProviderConfig("test-secret", models[kind])},
        provider_order=(kind,),
        timeout_seconds=8.0,
    )
    return registry.specs[0]


def _request() -> ProviderRequest:
    return ProviderRequest(
        messages=(
            ProviderMessage(MessageRole.SYSTEM, "system contract"),
            ProviderMessage(MessageRole.USER, "hello"),
        ),
        max_output_tokens=128,
        request_id="req-test",
    )


def _client_returning(response):
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, create


@pytest.mark.asyncio
async def test_groq_request_uses_low_hidden_reasoning_and_normalizes_usage() -> None:
    response = SimpleNamespace(
        model="openai/gpt-oss-120b",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="你好！", refusal=None),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, total_tokens=13),
    )
    client, create = _client_returning(response)
    provider = OpenAICompatibleProvider(_spec(), client=client)

    result = await provider.complete(_request())

    assert isinstance(result, ProviderCompletion)
    assert result.content == "你好！"
    assert result.usage is not None
    assert result.usage.total_tokens == 13
    kwargs = create.await_args.kwargs
    assert kwargs["max_completion_tokens"] == 128
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["extra_body"]["reasoning_format"] == "hidden"
    assert kwargs["messages"] == [
        {"role": "system", "content": "system contract"},
        {"role": "user", "content": "hello"},
    ]


@pytest.mark.asyncio
async def test_gemini_request_uses_minimal_reasoning() -> None:
    response = SimpleNamespace(
        model="gemini-3.5-flash",
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok"))],
        usage=None,
    )
    client, create = _client_returning(response)
    provider = OpenAICompatibleProvider(_spec(ProviderKind.GEMINI), client=client)

    result = await provider.complete(_request())

    assert isinstance(result, ProviderCompletion)
    assert create.await_args.kwargs["reasoning_effort"] == "minimal"
    assert "extra_body" not in create.await_args.kwargs


@pytest.mark.asyncio
async def test_openrouter_request_disables_reasoning_and_enforces_zero_price() -> None:
    response = SimpleNamespace(
        model="inclusionai/ling-3.0-flash-vl:free",
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok"))],
        usage=None,
    )
    client, create = _client_returning(response)
    provider = OpenAICompatibleProvider(_spec(ProviderKind.OPENROUTER), client=client)

    result = await provider.complete(_request())

    assert isinstance(result, ProviderCompletion)
    assert create.await_args.kwargs["extra_body"] == {
        "include_reasoning": False,
        "reasoning": {"enabled": False},
        "provider": {"max_price": {"prompt": 0, "completion": 0}},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(ProviderKind))
async def test_developer_role_maps_to_supported_system_role(kind: ProviderKind) -> None:
    response = SimpleNamespace(
        model=_spec(kind).model,
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok"))],
        usage=None,
    )
    client, create = _client_returning(response)
    provider = OpenAICompatibleProvider(_spec(kind), client=client)
    request = ProviderRequest(
        messages=(
            ProviderMessage(MessageRole.DEVELOPER, "trusted instructions"),
            ProviderMessage(MessageRole.USER, "hello"),
        ),
        max_output_tokens=128,
    )

    result = await provider.complete(request)

    assert isinstance(result, ProviderCompletion)
    assert create.await_args.kwargs["messages"][0] == {
        "role": "system",
        "content": "trusted instructions",
    }


@pytest.mark.asyncio
async def test_blank_completion_is_normalized_as_nonretryable_empty() -> None:
    response = SimpleNamespace(
        model="openai/gpt-oss-120b",
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="   "))],
        usage=None,
    )
    client, _ = _client_returning(response)
    provider = OpenAICompatibleProvider(_spec(), client=client)

    result = await provider.complete(_request())

    assert isinstance(result, ProviderFailure)
    assert result.kind is FailureKind.EMPTY
    assert result.retryable is False


@pytest.mark.asyncio
async def test_content_filter_is_terminal_safety_failure() -> None:
    response = SimpleNamespace(
        model="openai/gpt-oss-120b",
        choices=[
            SimpleNamespace(
                finish_reason="content_filter",
                message=SimpleNamespace(content=None, refusal="blocked"),
            )
        ],
        usage=None,
    )
    client, _ = _client_returning(response)
    provider = OpenAICompatibleProvider(_spec(), client=client)

    result = await provider.complete(_request())

    assert isinstance(result, ProviderFailure)
    assert result.kind is FailureKind.SAFETY
    assert result.retryable is False


def _response_error(error_type, status_code: int):
    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type("synthetic error", response=response, body=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "kind", "retryable"),
    [
        (
            APITimeoutError(request=httpx.Request("POST", "https://example.invalid")),
            FailureKind.TIMEOUT,
            True,
        ),
        (
            APIConnectionError(request=httpx.Request("POST", "https://example.invalid")),
            FailureKind.NETWORK,
            True,
        ),
        (_response_error(RateLimitError, 429), FailureKind.RATE_LIMITED, True),
        (_response_error(NotFoundError, 404), FailureKind.MODEL_UNAVAILABLE, True),
        (_response_error(InternalServerError, 503), FailureKind.SERVER_ERROR, True),
        (_response_error(AuthenticationError, 401), FailureKind.AUTHENTICATION, False),
        (_response_error(PermissionDeniedError, 403), FailureKind.PERMISSION, False),
        (_response_error(BadRequestError, 400), FailureKind.VALIDATION, False),
        (RuntimeError("synthetic"), FailureKind.UNKNOWN, False),
    ],
)
async def test_provider_exceptions_are_sanitized(
    error: Exception,
    kind: FailureKind,
    retryable: bool,
) -> None:
    create = AsyncMock(side_effect=error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = OpenAICompatibleProvider(_spec(), client=client)

    result = await provider.complete(_request())

    assert isinstance(result, ProviderFailure)
    assert result.kind is kind
    assert result.retryable is retryable
    assert not hasattr(result, "message")
