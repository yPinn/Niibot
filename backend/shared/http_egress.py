"""Host-scoped concurrency and circuit protection for outbound HTTP clients.

The wrapper deliberately does not cache responses or retry requests.  It limits
the number of live requests to each host, learns provider defer windows from
rate-limit headers, and temporarily opens a host circuit after repeated
transient failures.  Callers therefore keep ownership of application-specific
retry and cache semantics, especially for mutations and signed media URLs.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

_Sleep = Callable[[float], Awaitable[None]]
_Clock = Callable[[], float]
_TRANSIENT_STATUSES = frozenset({408, 425, 429})


class HostEgressError(RuntimeError):
    """Base error for locally rejected outbound requests."""


class HostCircuitOpenError(HostEgressError):
    """Raised when a host circuit is open or already running its probe."""


class HostEgressClosedError(HostEgressError):
    """Raised when a request waits on, or uses, a closed client."""


class HostStateCapacityError(HostEgressError):
    """Raised when every bounded host slot is currently in use."""


@dataclass(slots=True)
class _HostState:
    semaphore: asyncio.Semaphore
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    references: int = 0
    consecutive_failures: int = 0
    open_until: float = 0.0
    blocked_until: float = 0.0
    half_open_probe: bool = False


class HostEgressClient:
    """An ``httpx.AsyncClient`` facade with per-host failure isolation."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_concurrency_per_host: int = 2,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        default_retry_after_seconds: float = 5.0,
        max_defer_seconds: float = 300.0,
        max_hosts: int = 256,
        monotonic: _Clock = time.monotonic,
        wall_clock: _Clock = time.time,
        sleep: _Sleep = asyncio.sleep,
    ) -> None:
        if max_concurrency_per_host <= 0:
            raise ValueError("max_concurrency_per_host must be positive")
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")
        if default_retry_after_seconds <= 0 or max_defer_seconds <= 0:
            raise ValueError("defer durations must be positive")
        if max_hosts <= 0:
            raise ValueError("max_hosts must be positive")

        self._client = client
        self._max_concurrency_per_host = max_concurrency_per_host
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._default_retry_after_seconds = default_retry_after_seconds
        self._max_defer_seconds = max_defer_seconds
        self._max_hosts = max_hosts
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._hosts: OrderedDict[str, _HostState] = OrderedDict()
        self._closed = False

    async def request(
        self,
        method: str,
        url: str | httpx.URL,
        **kwargs: Any,
    ) -> httpx.Response:
        host_key, state = self._checkout(url)
        acquired = False
        try:
            await self._acquire(host_key, state)
            acquired = True
            try:
                try:
                    response = await self._client.request(method, url, **kwargs)
                except httpx.TransportError:
                    await self._record_transient_failure(state)
                    raise
                await self._observe_response(
                    state,
                    response.status_code,
                    response.headers,
                    allow_defer=method.upper() in {"GET", "HEAD"},
                )
                return response
            except BaseException:
                # A cancelled half-open request never reaches response
                # observation. Release its probe ownership so the host can
                # recover through a replacement probe instead of remaining
                # locally wedged forever.
                state.half_open_probe = False
                raise
        finally:
            if acquired:
                state.semaphore.release()
            self._checkin(host_key, state)

    async def get(self, url: str | httpx.URL, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def head(self, url: str | httpx.URL, **kwargs: Any) -> httpx.Response:
        return await self.request("HEAD", url, **kwargs)

    async def post(self, url: str | httpx.URL, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str | httpx.URL,
        **kwargs: Any,
    ) -> AsyncIterator[httpx.Response]:
        host_key, state = self._checkout(url)
        acquired = False
        try:
            await self._acquire(host_key, state)
            acquired = True
            try:
                try:
                    async with self._client.stream(method, url, **kwargs) as response:
                        await self._observe_response(
                            state,
                            response.status_code,
                            response.headers,
                            allow_defer=method.upper() in {"GET", "HEAD"},
                        )
                        yield response
                except httpx.TransportError:
                    await self._record_transient_failure(state)
                    raise
            except BaseException:
                state.half_open_probe = False
                raise
        finally:
            if acquired:
                state.semaphore.release()
            self._checkin(host_key, state)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Wake semaphore waiters.  Each awakened waiter rechecks ``_closed`` and
        # releases its permit, cascading to any remaining queued requests.
        for state in self._hosts.values():
            for _ in range(self._max_concurrency_per_host):
                state.semaphore.release()
        await self._client.aclose()

    def _checkout(self, url: str | httpx.URL) -> tuple[str, _HostState]:
        if self._closed:
            raise HostEgressClosedError("outbound HTTP client is closed")
        host_key = self._host_key(url)
        state = self._hosts.get(host_key)
        if state is None:
            self._evict_idle_hosts()
            if len(self._hosts) >= self._max_hosts:
                raise HostStateCapacityError("outbound HTTP host capacity is exhausted")
            state = _HostState(asyncio.Semaphore(self._max_concurrency_per_host))
            self._hosts[host_key] = state
        else:
            self._hosts.move_to_end(host_key)
        state.references += 1
        return host_key, state

    def _checkin(self, host_key: str, state: _HostState) -> None:
        state.references = max(0, state.references - 1)
        if host_key in self._hosts:
            self._hosts.move_to_end(host_key)

    def _evict_idle_hosts(self) -> None:
        while len(self._hosts) >= self._max_hosts:
            idle_key = next(
                (key for key, state in self._hosts.items() if state.references == 0),
                None,
            )
            if idle_key is None:
                return
            del self._hosts[idle_key]

    async def _acquire(self, host_key: str, state: _HostState) -> None:
        while True:
            if self._closed:
                raise HostEgressClosedError("outbound HTTP client is closed")
            await state.semaphore.acquire()
            delay = 0.0
            try:
                async with state.lock:
                    if self._closed:
                        raise HostEgressClosedError("outbound HTTP client is closed")
                    now = self._monotonic()
                    if state.open_until > now:
                        raise HostCircuitOpenError(f"outbound circuit is open for host {host_key}")
                    if state.half_open_probe:
                        raise HostCircuitOpenError(
                            f"outbound circuit probe is in progress for host {host_key}"
                        )
                    delay = max(0.0, state.blocked_until - now)
                    if delay <= 0.0:
                        if state.open_until > 0.0:
                            state.half_open_probe = True
                        return
            except BaseException:
                state.semaphore.release()
                raise

            state.semaphore.release()
            await self._sleep(delay)

    async def _observe_response(
        self,
        state: _HostState,
        status_code: int,
        headers: Mapping[str, Any],
        *,
        allow_defer: bool,
    ) -> None:
        if status_code in _TRANSIENT_STATUSES or status_code >= 500:
            delay = self._retry_delay(headers) if status_code == 429 and allow_defer else None
            await self._record_transient_failure(state, delay=delay)
            return
        async with state.lock:
            state.consecutive_failures = 0
            state.open_until = 0.0
            state.half_open_probe = False

    async def _record_transient_failure(
        self,
        state: _HostState,
        *,
        delay: float | None = None,
    ) -> None:
        async with state.lock:
            now = self._monotonic()
            if delay is not None:
                state.blocked_until = max(state.blocked_until, now + delay)
            state.consecutive_failures += 1
            state.half_open_probe = False
            if state.consecutive_failures >= self._failure_threshold:
                state.open_until = now + self._cooldown_seconds

    def _retry_delay(self, headers: Mapping[str, Any]) -> float:
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        raw_retry_after = normalized.get("retry-after")
        if raw_retry_after is not None:
            try:
                parsed = float(raw_retry_after)
                if parsed > 0:
                    return min(parsed, self._max_defer_seconds)
            except (TypeError, ValueError):
                pass

        for header in ("x-ratelimit-reset", "ratelimit-reset"):
            raw_reset = normalized.get(header)
            if raw_reset is None:
                continue
            try:
                parsed = float(raw_reset) - self._wall_clock()
                if parsed > 0:
                    return min(parsed, self._max_defer_seconds)
            except (TypeError, ValueError):
                pass

        return min(self._default_retry_after_seconds, self._max_defer_seconds)

    @staticmethod
    def _host_key(url: str | httpx.URL) -> str:
        parsed = urlsplit(str(url))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("outbound URL must use http or https and include a host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("outbound URL must not contain user info")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("outbound URL contains an invalid port") from exc
        return f"{parsed.hostname.lower()}:{port}" if port is not None else parsed.hostname.lower()
