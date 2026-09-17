"""Tests for bounded fallback, deadlines, and provider circuit state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from shared.assistant.contracts import (
    AssistantOutcome,
    FailureKind,
    MessageRole,
    ProviderCompletion,
    ProviderFailure,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
)
from shared.assistant.router import (
    BoundedAssistantRouter,
    CircuitState,
    RouterPolicy,
)


def _request() -> ProviderRequest:
    return ProviderRequest(
        messages=(ProviderMessage(MessageRole.USER, "hello"),),
        max_output_tokens=128,
        request_id="req-test",
    )


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeProvider:
    def __init__(
        self,
        name: str,
        model: str,
        responses: list[ProviderResponse],
        *,
        on_call: Callable[[], None] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.responses = responses
        self.on_call = on_call
        self.calls = 0

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        assert request == _request()
        self.calls += 1
        if self.on_call is not None:
            self.on_call()
        return self.responses.pop(0)


class HangingProvider:
    name = "hanging"
    model = "hanging-1"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _success(name: str, model: str, content: str = "ok") -> ProviderCompletion:
    return ProviderCompletion(provider=name, model=model, content=content)


def _failure(name: str, model: str, kind: FailureKind) -> ProviderFailure:
    return ProviderFailure(provider=name, model=model, kind=kind)


def _policy(**overrides) -> RouterPolicy:
    values = {
        "total_timeout_seconds": 1.0,
        "per_attempt_timeout_seconds": 0.2,
        "max_attempts": 3,
        "failure_threshold": 2,
        "cooldown_seconds": 30.0,
    }
    values.update(overrides)
    return RouterPolicy(**values)


@pytest.mark.asyncio
async def test_first_success_returns_one_attempt() -> None:
    provider = FakeProvider("primary", "p1", [_success("primary", "p1", "你好")])
    router = BoundedAssistantRouter((provider,), policy=_policy())

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.OK
    assert result.content == "你好"
    assert len(result.attempts) == 1
    assert result.attempts[0].succeeded is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMITED,
        FailureKind.NETWORK,
        FailureKind.SERVER_ERROR,
        FailureKind.MODEL_UNAVAILABLE,
    ],
)
async def test_retryable_failure_falls_back_to_next_provider(kind: FailureKind) -> None:
    primary = FakeProvider("primary", "p1", [_failure("primary", "p1", kind)])
    secondary = FakeProvider("secondary", "p2", [_success("secondary", "p2")])
    router = BoundedAssistantRouter((primary, secondary), policy=_policy())

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.OK
    assert result.provider == "secondary"
    assert [attempt.provider for attempt in result.attempts] == ["primary", "secondary"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "outcome"),
    [
        (FailureKind.AUTHENTICATION, AssistantOutcome.MISCONFIGURED),
        (FailureKind.PERMISSION, AssistantOutcome.MISCONFIGURED),
        (FailureKind.VALIDATION, AssistantOutcome.MISCONFIGURED),
        (FailureKind.SAFETY, AssistantOutcome.BLOCKED),
        (FailureKind.EMPTY, AssistantOutcome.EMPTY),
    ],
)
async def test_terminal_failure_does_not_fallback(
    kind: FailureKind,
    outcome: AssistantOutcome,
) -> None:
    primary = FakeProvider("primary", "p1", [_failure("primary", "p1", kind)])
    secondary = FakeProvider("secondary", "p2", [_success("secondary", "p2")])
    router = BoundedAssistantRouter((primary, secondary), policy=_policy())

    result = await router.route(_request())

    assert result.outcome is outcome
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_all_retryable_failures_preserve_attempt_metadata() -> None:
    providers = tuple(
        FakeProvider(
            f"provider-{index}",
            f"model-{index}",
            [_failure(f"provider-{index}", f"model-{index}", FailureKind.RATE_LIMITED)],
        )
        for index in range(3)
    )
    router = BoundedAssistantRouter(providers, policy=_policy())

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.UNAVAILABLE
    assert len(result.attempts) == 3
    assert all(attempt.failure is not None for attempt in result.attempts)


@pytest.mark.asyncio
async def test_attempt_limit_stops_before_fourth_provider() -> None:
    providers = tuple(
        FakeProvider(
            f"provider-{index}",
            f"model-{index}",
            [_failure(f"provider-{index}", f"model-{index}", FailureKind.TIMEOUT)],
        )
        for index in range(4)
    )
    router = BoundedAssistantRouter(providers, policy=_policy(max_attempts=3))

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.UNAVAILABLE
    assert [provider.calls for provider in providers] == [1, 1, 1, 0]


@pytest.mark.asyncio
async def test_per_attempt_timeout_is_normalized_and_falls_back() -> None:
    primary = HangingProvider()
    secondary = FakeProvider("secondary", "p2", [_success("secondary", "p2")])
    router = BoundedAssistantRouter(
        (primary, secondary),
        policy=_policy(per_attempt_timeout_seconds=0.01, total_timeout_seconds=0.2),
    )

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.OK
    assert result.attempts[0].failure is not None
    assert result.attempts[0].failure.kind is FailureKind.TIMEOUT
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_total_deadline_stops_before_next_provider() -> None:
    clock = FakeClock()
    primary = FakeProvider(
        "primary",
        "p1",
        [_failure("primary", "p1", FailureKind.RATE_LIMITED)],
        on_call=lambda: clock.advance(1.1),
    )
    secondary = FakeProvider("secondary", "p2", [_success("secondary", "p2")])
    router = BoundedAssistantRouter(
        (primary, secondary),
        policy=_policy(total_timeout_seconds=1.0),
        clock=clock,
    )

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.UNAVAILABLE
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_circuit_opens_then_half_open_success_recovers() -> None:
    clock = FakeClock()
    primary = FakeProvider(
        "primary",
        "p1",
        [
            _failure("primary", "p1", FailureKind.RATE_LIMITED),
            _failure("primary", "p1", FailureKind.RATE_LIMITED),
            _success("primary", "p1"),
        ],
    )
    secondary = FakeProvider(
        "secondary",
        "p2",
        [_success("secondary", "p2") for _ in range(3)],
    )
    router = BoundedAssistantRouter(
        (primary, secondary),
        policy=_policy(failure_threshold=2, cooldown_seconds=30.0),
        clock=clock,
    )

    await router.route(_request())
    await router.route(_request())
    assert router.provider_health()[0].state is CircuitState.OPEN

    await router.route(_request())
    assert primary.calls == 2

    clock.advance(31.0)
    assert router.provider_health()[0].state is CircuitState.HALF_OPEN
    recovered = await router.route(_request())

    assert recovered.provider == "primary"
    assert router.provider_health()[0].state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_auth_failure_marks_provider_unhealthy_for_future_requests() -> None:
    primary = FakeProvider(
        "primary",
        "p1",
        [_failure("primary", "p1", FailureKind.AUTHENTICATION)],
    )
    secondary = FakeProvider("secondary", "p2", [_success("secondary", "p2")])
    router = BoundedAssistantRouter((primary, secondary), policy=_policy())

    first = await router.route(_request())
    second = await router.route(_request())

    assert first.outcome is AssistantOutcome.MISCONFIGURED
    assert router.provider_health()[0].state is CircuitState.UNHEALTHY
    assert second.provider == "secondary"
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_no_configured_providers_returns_misconfigured() -> None:
    router = BoundedAssistantRouter((), policy=_policy())

    result = await router.route(_request())

    assert result.outcome is AssistantOutcome.MISCONFIGURED
    assert result.attempts == ()
