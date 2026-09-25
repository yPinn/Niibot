"""Bounded admission for the Scrapling sidecar's single browser session."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

import pytest
from scrapling import browser_admission
from scrapling.browser_admission import BrowserAdmission, BrowserBusyError


@pytest.mark.asyncio
async def test_simultaneous_arrival_cannot_bypass_zero_depth_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = BrowserAdmission(max_queue_depth=0, max_wait_seconds=1.0)
    release = asyncio.Event()
    real_wait_for = asyncio.wait_for

    async def delayed_wait_for(awaitable: Awaitable[Any], timeout: float) -> Any:
        await asyncio.sleep(0)
        return await real_wait_for(awaitable, timeout)

    monkeypatch.setattr(browser_admission.asyncio, "wait_for", delayed_wait_for)

    async def hold() -> None:
        async with admission.acquire():
            await release.wait()

    first = asyncio.create_task(hold())
    second = asyncio.create_task(hold())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    outcomes = (first.done(), second.done())
    assert outcomes.count(True) == 1
    rejected = first if first.done() else second
    active = second if first.done() else first
    with pytest.raises(BrowserBusyError):
        await rejected

    release.set()
    await active


@pytest.mark.asyncio
async def test_browser_jobs_are_strictly_serialized() -> None:
    admission = BrowserAdmission(max_queue_depth=2, max_wait_seconds=1.0)
    release = asyncio.Event()
    first_started = asyncio.Event()
    active = 0
    peak = 0

    async def job(name: str) -> str:
        nonlocal active, peak
        async with admission.acquire():
            active += 1
            peak = max(peak, active)
            try:
                if name == "first":
                    first_started.set()
                    await release.wait()
                return name
            finally:
                active -= 1

    first = asyncio.create_task(job("first"))
    await first_started.wait()
    second = asyncio.create_task(job("second"))
    await asyncio.sleep(0)
    assert not second.done()

    release.set()
    assert await asyncio.gather(first, second) == ["first", "second"]
    assert peak == 1


@pytest.mark.asyncio
async def test_browser_queue_rejects_work_beyond_its_bound() -> None:
    admission = BrowserAdmission(max_queue_depth=1, max_wait_seconds=1.0)
    release = asyncio.Event()
    first_started = asyncio.Event()

    async def hold() -> None:
        async with admission.acquire():
            first_started.set()
            await release.wait()

    first = asyncio.create_task(hold())
    await first_started.wait()
    queued = asyncio.create_task(hold())
    await asyncio.sleep(0)

    with pytest.raises(BrowserBusyError):
        async with admission.acquire():
            pass

    release.set()
    await asyncio.gather(first, queued)


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_consume_queue_capacity() -> None:
    admission = BrowserAdmission(max_queue_depth=1, max_wait_seconds=1.0)
    release = asyncio.Event()
    first_started = asyncio.Event()

    async def hold() -> None:
        async with admission.acquire():
            first_started.set()
            await release.wait()

    first = asyncio.create_task(hold())
    await first_started.wait()
    cancelled = asyncio.create_task(hold())
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    replacement = asyncio.create_task(hold())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, replacement)
