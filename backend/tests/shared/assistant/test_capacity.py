"""Tests for provider-wide token budgets and fair bounded admission."""

from __future__ import annotations

import asyncio

import pytest

from shared.assistant.capacity import (
    ProviderBudgetPolicy,
    ProviderCapacityController,
    estimate_request_tokens,
)
from shared.assistant.contracts import (
    MessageRole,
    ProviderMessage,
    ProviderRequest,
)


def _request(*, max_output_tokens: int = 100) -> ProviderRequest:
    return ProviderRequest(
        messages=(
            ProviderMessage(MessageRole.SYSTEM, "system policy"),
            ProviderMessage(MessageRole.USER, "你好 hello"),
        ),
        max_output_tokens=max_output_tokens,
        scheduling_scope="channel-a",
    )


def _policy(**overrides: object) -> ProviderBudgetPolicy:
    values: dict[str, object] = {
        "requests_per_minute": 100,
        "tokens_per_minute": 100,
        "max_queue_depth": 4,
        "max_wait_seconds": 0.2,
    }
    values.update(overrides)
    return ProviderBudgetPolicy(**values)  # type: ignore[arg-type]


def test_token_estimate_includes_messages_output_and_protocol_overhead() -> None:
    request = _request(max_output_tokens=100)

    estimate = estimate_request_tokens(request)

    assert estimate > request.max_output_tokens
    assert estimate < sum(len(message.content) for message in request.messages) + 120


@pytest.mark.asyncio
async def test_missing_policy_allows_provider_without_creating_a_lease() -> None:
    controller = ProviderCapacityController({})

    decision = await controller.admit(
        "unlimited",
        "model",
        scope="channel-a",
        estimated_tokens=100,
    )

    assert decision.admitted is True
    assert decision.lease is None


@pytest.mark.asyncio
async def test_budgets_are_isolated_by_provider_and_model() -> None:
    controller = ProviderCapacityController(
        {
            ("primary", "p1"): _policy(tokens_per_minute=100),
            ("secondary", "p2"): _policy(tokens_per_minute=100),
        }
    )
    first = await controller.admit("primary", "p1", scope="channel-a", estimated_tokens=100)

    blocked = await controller.admit(
        "primary",
        "p1",
        scope="channel-b",
        estimated_tokens=100,
        max_wait_seconds=0,
    )
    secondary = await controller.admit("secondary", "p2", scope="channel-b", estimated_tokens=100)

    assert first.admitted is True
    assert blocked.admitted is False
    assert secondary.admitted is True


@pytest.mark.asyncio
async def test_waiting_channels_are_served_round_robin_not_by_noisy_channel() -> None:
    controller = ProviderCapacityController({("p", "m"): _policy()})
    first = await controller.admit("p", "m", scope="channel-a", estimated_tokens=100)
    assert first.lease is not None

    same_channel = asyncio.create_task(
        controller.admit("p", "m", scope="channel-a", estimated_tokens=100)
    )
    await asyncio.sleep(0)
    other_channel = asyncio.create_task(
        controller.admit("p", "m", scope="channel-b", estimated_tokens=100)
    )
    await asyncio.sleep(0)

    await controller.reconcile(first.lease, actual_tokens=0)
    other_decision = await asyncio.wait_for(other_channel, timeout=0.2)

    assert other_decision.admitted is True
    assert same_channel.done() is False
    assert other_decision.lease is not None

    await controller.reconcile(other_decision.lease, actual_tokens=0)
    same_decision = await asyncio.wait_for(same_channel, timeout=0.2)
    assert same_decision.admitted is True


@pytest.mark.asyncio
async def test_queue_is_bounded_and_cancelled_waiter_does_not_leak() -> None:
    controller = ProviderCapacityController(
        {("p", "m"): _policy(max_queue_depth=1, max_wait_seconds=1.0)}
    )
    first = await controller.admit("p", "m", scope="channel-a", estimated_tokens=100)
    assert first.lease is not None

    waiting = asyncio.create_task(
        controller.admit("p", "m", scope="channel-b", estimated_tokens=100)
    )
    await asyncio.sleep(0)
    shed = await controller.admit(
        "p",
        "m",
        scope="channel-c",
        estimated_tokens=100,
        max_wait_seconds=0,
    )
    assert shed.admitted is False

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await controller.reconcile(first.lease, actual_tokens=0)

    recovered = await controller.admit(
        "p",
        "m",
        scope="channel-c",
        estimated_tokens=100,
        max_wait_seconds=0,
    )
    assert recovered.admitted is True


@pytest.mark.asyncio
async def test_actual_usage_replaces_conservative_token_reservation() -> None:
    controller = ProviderCapacityController({("p", "m"): _policy(tokens_per_minute=150)})
    first = await controller.admit("p", "m", scope="channel-a", estimated_tokens=100)
    assert first.lease is not None

    await controller.reconcile(first.lease, actual_tokens=40)
    second = await controller.admit(
        "p",
        "m",
        scope="channel-b",
        estimated_tokens=100,
        max_wait_seconds=0,
    )

    assert second.admitted is True
    snapshot = controller.snapshots()[0]
    assert snapshot.minute_requests == 2
    assert snapshot.minute_tokens == 140
    assert snapshot.queued_requests == 0


@pytest.mark.asyncio
async def test_cancelled_preflight_reservation_frees_request_and_token_capacity() -> None:
    controller = ProviderCapacityController(
        {
            ("p", "m"): ProviderBudgetPolicy(
                requests_per_minute=1,
                tokens_per_minute=100,
                max_queue_depth=0,
                max_wait_seconds=0,
            )
        }
    )
    first = await controller.admit("p", "m", scope="channel-a", estimated_tokens=100)
    assert first.lease is not None

    await controller.cancel(first.lease)
    replacement = await controller.admit("p", "m", scope="channel-b", estimated_tokens=100)

    assert replacement.admitted is True
