"""Host-scoped concurrency and circuit contracts for outbound HTTP."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from shared.http_egress import (
    HostCircuitOpenError,
    HostEgressClient,
    HostEgressClosedError,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.wall_now = 1_000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.wall_now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay
        self.wall_now += delay

    def advance(self, delay: float) -> None:
        self.now += delay
        self.wall_now += delay


def _response(status_code: int, **headers: str) -> httpx.Response:
    return httpx.Response(status_code, headers=headers)


async def _wait_for_calls(mock: AsyncMock, expected: int) -> None:
    for _ in range(20):
        if mock.await_count >= expected:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"expected {expected} calls, got {mock.await_count}")


@pytest.mark.asyncio
async def test_same_host_burst_never_exceeds_configured_concurrency() -> None:
    release = asyncio.Event()
    active = 0
    peak = 0

    async def request(*_args: object, **_kwargs: object) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await release.wait()
            return _response(200)
        finally:
            active -= 1

    raw = MagicMock()
    raw.request = AsyncMock(side_effect=request)
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw, max_concurrency_per_host=2)

    tasks = [asyncio.create_task(client.get("https://cdn.example/item")) for _ in range(3)]
    await _wait_for_calls(raw.request, 2)
    assert raw.request.await_count == 2
    assert peak == 2

    release.set()
    await asyncio.gather(*tasks)
    await client.aclose()


@pytest.mark.asyncio
async def test_slow_host_does_not_block_a_different_host() -> None:
    release = asyncio.Event()
    slow_started = asyncio.Event()

    async def request(_method: str, url: str, **_kwargs: object) -> httpx.Response:
        if "slow.example" in url:
            slow_started.set()
            await release.wait()
        return _response(200)

    raw = MagicMock()
    raw.request = AsyncMock(side_effect=request)
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw, max_concurrency_per_host=1)

    slow = asyncio.create_task(client.get("https://slow.example/item"))
    await slow_started.wait()
    await asyncio.wait_for(client.get("https://fast.example/item"), timeout=0.1)

    release.set()
    await slow
    await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_consume_a_host_permit() -> None:
    release = asyncio.Event()
    first_started = asyncio.Event()

    async def request(*_args: object, **_kwargs: object) -> httpx.Response:
        first_started.set()
        await release.wait()
        return _response(200)

    raw = MagicMock()
    raw.request = AsyncMock(side_effect=request)
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw, max_concurrency_per_host=1)

    first = asyncio.create_task(client.get("https://cdn.example/first"))
    await first_started.wait()
    cancelled = asyncio.create_task(client.get("https://cdn.example/cancelled"))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    release.set()
    await first
    await asyncio.wait_for(client.get("https://cdn.example/after"), timeout=0.1)
    await client.aclose()


@pytest.mark.asyncio
async def test_retry_after_defers_only_the_affected_host() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.request = AsyncMock(
        side_effect=[
            _response(429, **{"Retry-After": "7"}),
            _response(200),
            _response(200),
        ]
    )
    raw.aclose = AsyncMock()
    client = HostEgressClient(
        raw,
        failure_threshold=3,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
        sleep=clock.sleep,
    )

    await client.get("https://limited.example/one")
    await client.get("https://other.example/two")
    assert clock.sleeps == []

    await client.get("https://limited.example/three")
    assert clock.sleeps == [pytest.approx(7.0)]
    await client.aclose()


@pytest.mark.asyncio
async def test_reset_epoch_is_used_when_retry_after_is_absent() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.request = AsyncMock(
        side_effect=[
            _response(429, **{"X-RateLimit-Reset": "1004"}),
            _response(200),
        ]
    )
    raw.aclose = AsyncMock()
    client = HostEgressClient(
        raw,
        failure_threshold=3,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
        sleep=clock.sleep,
    )

    await client.get("https://limited.example/one")
    await client.get("https://limited.example/two")

    assert clock.sleeps == [pytest.approx(4.0)]
    await client.aclose()


@pytest.mark.asyncio
async def test_repeated_transient_responses_open_only_that_host_circuit() -> None:
    raw = MagicMock()
    raw.request = AsyncMock(side_effect=[_response(500), _response(503), _response(200)])
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw, failure_threshold=2, cooldown_seconds=30.0)

    await client.get("https://failing.example/one")
    await client.get("https://failing.example/two")
    with pytest.raises(HostCircuitOpenError):
        await client.get("https://failing.example/three")

    await client.get("https://healthy.example/one")
    assert raw.request.await_count == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_only_one_half_open_probe_runs_and_success_recovers() -> None:
    clock = _Clock()
    probe_started = asyncio.Event()
    release_probe = asyncio.Event()

    async def probe(*_args: object, **_kwargs: object) -> httpx.Response:
        probe_started.set()
        await release_probe.wait()
        return _response(200)

    request_count = 0

    async def request(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return _response(500)
        if request_count == 2:
            return await probe(*args, **kwargs)
        return _response(200)

    raw = MagicMock()
    raw.request = AsyncMock(side_effect=request)
    raw.aclose = AsyncMock()
    client = HostEgressClient(
        raw,
        failure_threshold=1,
        cooldown_seconds=10.0,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
        sleep=clock.sleep,
    )

    await client.get("https://recover.example/first")
    with pytest.raises(HostCircuitOpenError):
        await client.get("https://recover.example/blocked")

    clock.advance(10.0)
    half_open = asyncio.create_task(client.get("https://recover.example/probe"))
    await probe_started.wait()
    with pytest.raises(HostCircuitOpenError):
        await client.get("https://recover.example/parallel")

    release_probe.set()
    await half_open
    await client.get("https://recover.example/recovered")
    await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_half_open_probe_does_not_wedge_the_host() -> None:
    clock = _Clock()
    probe_started = asyncio.Event()
    release_probe = asyncio.Event()
    request_count = 0

    async def request(*_args: object, **_kwargs: object) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return _response(500)
        if request_count == 2:
            probe_started.set()
            await release_probe.wait()
        return _response(200)

    raw = MagicMock()
    raw.request = AsyncMock(side_effect=request)
    raw.aclose = AsyncMock()
    client = HostEgressClient(
        raw,
        failure_threshold=1,
        cooldown_seconds=10.0,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
        sleep=clock.sleep,
    )

    await client.get("https://recover.example/first")
    clock.advance(10.0)
    cancelled = asyncio.create_task(client.get("https://recover.example/cancelled-probe"))
    await probe_started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    recovered = await client.get("https://recover.example/replacement-probe")

    assert recovered.status_code == 200
    assert request_count == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_half_open_probe_waits_for_a_longer_retry_after_window() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.request = AsyncMock(
        side_effect=[
            _response(429, **{"Retry-After": "20"}),
            _response(200),
        ]
    )
    raw.aclose = AsyncMock()
    client = HostEgressClient(
        raw,
        failure_threshold=1,
        cooldown_seconds=10.0,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
        sleep=clock.sleep,
    )

    await client.get("https://recover.example/limited")
    clock.advance(10.0)
    response = await client.get("https://recover.example/probe")

    assert response.status_code == 200
    assert clock.sleeps == [pytest.approx(10.0)]
    await client.aclose()


@pytest.mark.asyncio
async def test_post_failure_is_never_retried() -> None:
    raw = MagicMock()
    raw.request = AsyncMock(return_value=_response(503))
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw)

    response = await client.post("https://auth.example/token", data={"grant_type": "client"})

    assert response.status_code == 503
    raw.request.assert_awaited_once()
    await client.aclose()


@pytest.mark.asyncio
async def test_post_429_does_not_apply_a_retry_after_delay() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.request = AsyncMock(
        side_effect=[
            _response(429, **{"Retry-After": "20"}),
            _response(200),
        ]
    )
    raw.aclose = AsyncMock()
    client = HostEgressClient(
        raw,
        failure_threshold=3,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
        sleep=clock.sleep,
    )

    await client.post("https://auth.example/token")
    await client.post("https://auth.example/token")

    assert clock.sleeps == []
    await client.aclose()


@pytest.mark.asyncio
async def test_signed_stream_url_is_fetched_again_instead_of_cached() -> None:
    response = _response(200)

    @asynccontextmanager
    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[httpx.Response]:
        yield response

    raw = MagicMock()
    raw.stream = MagicMock(side_effect=stream)
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw)
    signed_url = "https://cdn.example/video.mp4?token=secret&expires=123"

    async with client.stream("GET", signed_url):
        pass
    async with client.stream("GET", signed_url):
        pass

    assert raw.stream.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_close_wakes_queued_requests_and_closes_underlying_client() -> None:
    release = asyncio.Event()
    first_started = asyncio.Event()

    async def request(*_args: object, **_kwargs: object) -> httpx.Response:
        first_started.set()
        await release.wait()
        return _response(200)

    raw = MagicMock()
    raw.request = AsyncMock(side_effect=request)
    raw.aclose = AsyncMock()
    client = HostEgressClient(raw, max_concurrency_per_host=1)

    first = asyncio.create_task(client.get("https://cdn.example/first"))
    await first_started.wait()
    queued = asyncio.create_task(client.get("https://cdn.example/queued"))
    await asyncio.sleep(0)

    await client.aclose()
    with pytest.raises(HostEgressClosedError):
        await asyncio.wait_for(queued, timeout=0.1)
    raw.aclose.assert_awaited_once()

    release.set()
    await first
