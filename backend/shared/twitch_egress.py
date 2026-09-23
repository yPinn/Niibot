"""Shared in-process coordination for Twitch Helix and chat egress.

The coordinator keeps provider buckets distinct:

* Helix is keyed by the credential/app bucket and learns reset windows from
  response headers.
* Chat is keyed globally by sender across every channel, plus a conservative
  per-sender/per-channel interval.

Waiters are priority ordered and cancellation safe.  This module deliberately
does not retry mutations; callers may retry idempotent reads after a 429.
"""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import itertools
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


def credential_bucket_key(token: str | None) -> str:
    """Return a non-secret, stable in-process key for a Twitch credential."""
    if not token:
        return "app"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"token:{digest}"


class EgressPriority(IntEnum):
    """Lower values leave the queue first."""

    INTERACTIVE = 0
    NORMAL = 10
    BACKGROUND = 20


@dataclass(order=True, slots=True)
class _Waiter:
    priority: int
    sequence: int
    future: asyncio.Future[None] = field(compare=False)


@dataclass(slots=True)
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)
    waiters: list[_Waiter] = field(default_factory=list)
    blocked_until: float = 0.0
    last_grant: float | None = None
    worker: asyncio.Task[None] | None = None


class _PriorityWindowGate:
    def __init__(self, *, limit: int, window: float, min_interval: float = 0.0) -> None:
        if limit <= 0 or window <= 0 or min_interval < 0:
            raise ValueError("invalid rate gate configuration")
        self._limit = limit
        self._window = window
        self._min_interval = min_interval
        self._buckets: dict[str, _Bucket] = {}
        self._sequence = itertools.count()
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    def _bucket(self, key: str) -> _Bucket:
        return self._buckets.setdefault(key, _Bucket())

    async def acquire(self, key: str, *, priority: EgressPriority) -> None:
        if self._closed:
            raise RuntimeError("Twitch egress coordinator is closed")
        loop = asyncio.get_running_loop()
        bucket = self._bucket(key)
        future = loop.create_future()
        heapq.heappush(bucket.waiters, _Waiter(int(priority), next(self._sequence), future))
        self._ensure_worker(key, bucket)
        try:
            await future
        except asyncio.CancelledError:
            future.cancel()
            raise

    def defer(self, key: str, delay: float) -> None:
        if delay <= 0:
            return
        bucket = self._bucket(key)
        bucket.blocked_until = max(bucket.blocked_until, time.monotonic() + delay)
        if bucket.waiters:
            self._ensure_worker(key, bucket)

    def _ensure_worker(self, key: str, bucket: _Bucket) -> None:
        if bucket.worker is not None and not bucket.worker.done():
            return
        task = asyncio.create_task(self._run_bucket(key, bucket))
        bucket.worker = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_bucket(self, key: str, bucket: _Bucket) -> None:
        try:
            while bucket.waiters and not self._closed:
                while bucket.waiters and bucket.waiters[0].future.done():
                    heapq.heappop(bucket.waiters)
                if not bucket.waiters:
                    break

                now = time.monotonic()
                cutoff = now - self._window
                while bucket.timestamps and bucket.timestamps[0] <= cutoff:
                    bucket.timestamps.popleft()

                delay = max(0.0, bucket.blocked_until - now)
                if len(bucket.timestamps) >= self._limit:
                    delay = max(delay, bucket.timestamps[0] + self._window - now)
                if bucket.last_grant is not None:
                    delay = max(delay, bucket.last_grant + self._min_interval - now)
                if delay > 0:
                    await asyncio.sleep(delay)
                    continue

                waiter = heapq.heappop(bucket.waiters)
                if waiter.future.done():
                    continue
                granted_at = time.monotonic()
                bucket.timestamps.append(granted_at)
                bucket.last_grant = granted_at
                waiter.future.set_result(None)
        finally:
            bucket.worker = None
            if bucket.waiters and not self._closed:
                self._ensure_worker(key, bucket)

    async def close(self) -> None:
        self._closed = True
        for bucket in self._buckets.values():
            for waiter in bucket.waiters:
                waiter.future.cancel()
            bucket.waiters.clear()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


class TwitchEgressCoordinator:
    """Header-aware Twitch request coordinator with separate chat buckets."""

    def __init__(
        self,
        *,
        helix_limit: int = 720,
        helix_window: float = 60.0,
        helix_min_interval: float = 0.05,
        chat_sender_limit: int = 18,
        chat_sender_window: float = 30.0,
        chat_channel_interval: float = 1.1,
    ) -> None:
        self._helix = _PriorityWindowGate(
            limit=helix_limit,
            window=helix_window,
            min_interval=helix_min_interval,
        )
        self._chat_sender = _PriorityWindowGate(
            limit=chat_sender_limit,
            window=chat_sender_window,
        )
        self._chat_channel = _PriorityWindowGate(
            limit=1,
            window=max(chat_channel_interval, 0.001),
            min_interval=chat_channel_interval,
        )

    async def acquire_helix(
        self,
        bucket_key: str,
        *,
        priority: EgressPriority = EgressPriority.NORMAL,
    ) -> None:
        await self._helix.acquire(bucket_key, priority=priority)

    async def acquire_chat(
        self,
        sender_id: str,
        channel_id: str,
        *,
        priority: EgressPriority = EgressPriority.INTERACTIVE,
    ) -> None:
        await self._chat_channel.acquire(
            f"{sender_id}:{channel_id}",
            priority=priority,
        )
        await self._chat_sender.acquire(sender_id, priority=priority)

    def defer_chat(self, sender_id: str, channel_id: str, delay: float) -> None:
        """Defer both chat buckets after a provider-side send limit signal."""
        self._chat_channel.defer(f"{sender_id}:{channel_id}", delay)
        self._chat_sender.defer(sender_id, delay)

    def observe_helix(
        self,
        bucket_key: str,
        *,
        status_code: int,
        headers: Mapping[str, Any],
    ) -> float | None:
        """Apply provider reset headers and return the imposed delay, if any."""
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        delay: float | None = None

        retry_after = normalized.get("retry-after")
        if retry_after is not None:
            try:
                parsed = float(retry_after)
                if parsed > 0:
                    delay = parsed
            except (TypeError, ValueError):
                pass

        remaining = normalized.get("ratelimit-remaining")
        reset = normalized.get("ratelimit-reset")
        exhausted = status_code == 429
        if remaining is not None:
            try:
                exhausted = exhausted or int(remaining) <= 0
            except (TypeError, ValueError):
                pass
        if exhausted and delay is None and reset is not None:
            try:
                delay = max(float(reset) - time.time(), 0.0)
            except (TypeError, ValueError):
                pass
        if status_code == 429 and (delay is None or delay <= 0):
            delay = 5.0

        if delay is not None and delay > 0:
            self._helix.defer(bucket_key, delay)
            return delay
        return None

    async def close(self) -> None:
        await asyncio.gather(
            self._helix.close(),
            self._chat_sender.close(),
            self._chat_channel.close(),
        )
