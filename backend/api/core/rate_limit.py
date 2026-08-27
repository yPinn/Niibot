"""In-process sliding-window rate limiter — zero external dependency."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    """Sliding-window counter per arbitrary string key.

    In-process only: resets on restart and is not multi-instance safe.
    For single-process deployments this is sufficient.
    """

    _SWEEP_INTERVAL = 500  # calls between idle-key eviction sweeps

    def __init__(self, max_calls: int, period: float) -> None:
        self._max = max_calls
        self._period = period
        self._log: dict[str, deque[float]] = defaultdict(deque)
        self._calls_since_sweep = 0

    def allow(self, key: str) -> bool:
        """Record attempt. Returns True if within limit, False if exceeded."""
        now = time.monotonic()
        cutoff = now - self._period
        log = self._log[key]
        while log and log[0] < cutoff:
            log.popleft()
        allowed = len(log) < self._max
        if allowed:
            log.append(now)
        self._maybe_sweep(now)
        return allowed

    def _maybe_sweep(self, now: float) -> None:
        """Evict keys whose window has fully expired, bounding dict growth.

        Runs every _SWEEP_INTERVAL calls rather than on every call — sweeping
        an unbounded number of keys per request would defeat the point of an
        in-process rate limiter.
        """
        self._calls_since_sweep += 1
        if self._calls_since_sweep < self._SWEEP_INTERVAL:
            return
        self._calls_since_sweep = 0

        cutoff = now - self._period
        stale_keys = []
        for stale_key, log in self._log.items():
            while log and log[0] < cutoff:
                log.popleft()
            if not log:
                stale_keys.append(stale_key)
        for stale_key in stale_keys:
            del self._log[stale_key]

    def require(self, key: str) -> None:
        """Raise HTTP 429 if rate limit is exceeded."""
        if not self.allow(key):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
