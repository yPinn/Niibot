"""Tests for provider-wide token budgets and fair bounded admission."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from shared.assistant.capacity import (
    CAPACITY_DEPLOYMENT_MODE,
    ProviderBudgetPolicy,
    ProviderCapacityController,
    capacity_deployment_guard,
    discord_free_tier_budgets,
    estimate_request_tokens,
    provider_account_ceilings,
    twitch_free_tier_budgets,
)
from shared.assistant.contracts import (
    MessageRole,
    ProviderMessage,
    ProviderRequest,
)
from shared.assistant.providers.registry import ProviderKind


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


def test_partitioned_runtime_budgets_fit_shared_provider_ceilings() -> None:
    twitch = twitch_free_tier_budgets()
    discord = discord_free_tier_budgets()

    for provider, ceiling in provider_account_ceilings().items():
        policies = [budget for budgets in (twitch, discord) if (budget := budgets.get(provider))]
        for field in ("requests_per_minute", "tokens_per_minute", "requests_per_day"):
            provider_limit = getattr(ceiling, field)
            if provider_limit is None:
                continue
            allocated = sum(getattr(policy, field) or 0 for policy in policies)
            assert allocated <= provider_limit, (provider, field, allocated, provider_limit)

    assert (
        sum(budgets[ProviderKind.GROQ].requests_per_minute for budgets in (twitch, discord)) == 27
    )
    assert (
        sum(budgets[ProviderKind.OPENROUTER].requests_per_day for budgets in (twitch, discord))
        == 900
    )


def test_capacity_deployment_guard_declares_single_replica_boundary() -> None:
    for runtime in ("twitch", "discord"):
        guard = capacity_deployment_guard(runtime)
        assert guard.mode == CAPACITY_DEPLOYMENT_MODE == "partitioned-local"
        assert guard.runtime == runtime
        assert guard.max_replicas == 1
        assert guard.distributed is False
        assert guard.shared_provider_accounts is True


def test_production_compose_keeps_ai_runtimes_unscaled() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    base_compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (repo_root / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "container_name: nb-twitch" in base_compose
    assert "container_name: nb-discord" in base_compose
    assert "replicas:" not in base_compose
    assert "replicas:" not in prod_compose


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
