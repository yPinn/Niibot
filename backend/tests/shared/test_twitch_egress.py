"""Priority, fairness, cancellation, and reset semantics for Twitch egress."""

from __future__ import annotations

import asyncio

import pytest

from shared.twitch_egress import EgressPriority, TwitchEgressCoordinator


@pytest.mark.asyncio
async def test_helix_burst_is_spread_across_the_window() -> None:
    egress = TwitchEgressCoordinator(
        helix_limit=1,
        helix_window=0.03,
        helix_min_interval=0.0,
    )
    try:
        await egress.acquire_helix("user:1")
        started = asyncio.get_running_loop().time()
        await egress.acquire_helix("user:1")
        assert asyncio.get_running_loop().time() - started >= 0.02
    finally:
        await egress.close()


@pytest.mark.asyncio
async def test_higher_priority_overtakes_an_earlier_background_waiter() -> None:
    egress = TwitchEgressCoordinator(
        helix_limit=1,
        helix_window=0.04,
        helix_min_interval=0.0,
    )
    order: list[str] = []

    async def wait(name: str, priority: EgressPriority) -> None:
        await egress.acquire_helix("user:1", priority=priority)
        order.append(name)

    try:
        await egress.acquire_helix("user:1")
        low = asyncio.create_task(wait("background", EgressPriority.BACKGROUND))
        await asyncio.sleep(0)
        high = asyncio.create_task(wait("interactive", EgressPriority.INTERACTIVE))
        await asyncio.gather(high, low)
        assert order == ["interactive", "background"]
    finally:
        await egress.close()


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_stall_the_bucket() -> None:
    egress = TwitchEgressCoordinator(
        helix_limit=1,
        helix_window=0.03,
        helix_min_interval=0.0,
    )
    try:
        await egress.acquire_helix("user:1")
        cancelled = asyncio.create_task(egress.acquire_helix("user:1"))
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        await asyncio.wait_for(egress.acquire_helix("user:1"), timeout=0.2)
    finally:
        await egress.close()


@pytest.mark.asyncio
async def test_429_retry_after_defers_only_the_affected_helix_bucket() -> None:
    egress = TwitchEgressCoordinator(
        helix_limit=100,
        helix_window=1.0,
        helix_min_interval=0.0,
    )
    try:
        delay = egress.observe_helix(
            "user:limited",
            status_code=429,
            headers={"Retry-After": "0.03"},
        )
        assert delay == pytest.approx(0.03)

        unaffected = asyncio.create_task(egress.acquire_helix("user:other"))
        started = asyncio.get_running_loop().time()
        limited = asyncio.create_task(egress.acquire_helix("user:limited"))
        await unaffected
        assert not limited.done()
        await limited
        assert asyncio.get_running_loop().time() - started >= 0.02
    finally:
        await egress.close()


@pytest.mark.asyncio
async def test_chat_sender_limit_is_shared_across_channels() -> None:
    egress = TwitchEgressCoordinator(
        chat_sender_limit=1,
        chat_sender_window=0.03,
        chat_channel_interval=0.0,
    )
    try:
        await egress.acquire_chat("bot-1", "channel-1")
        started = asyncio.get_running_loop().time()
        await egress.acquire_chat("bot-1", "channel-2")
        assert asyncio.get_running_loop().time() - started >= 0.02
    finally:
        await egress.close()


@pytest.mark.asyncio
async def test_chat_per_channel_interval_does_not_block_other_channels() -> None:
    egress = TwitchEgressCoordinator(
        chat_sender_limit=100,
        chat_sender_window=1.0,
        chat_channel_interval=0.03,
    )
    try:
        await egress.acquire_chat("bot-1", "channel-1")
        other = asyncio.create_task(egress.acquire_chat("bot-1", "channel-2"))
        same = asyncio.create_task(egress.acquire_chat("bot-1", "channel-1"))
        await other
        assert not same.done()
        await same
    finally:
        await egress.close()
