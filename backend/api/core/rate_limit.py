"""In-process sliding-window rate limiter — zero external dependency."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    """Sliding-window counter per arbitrary string key.

    In-process only: resets on restart and is not multi-instance safe.
    For single-process deployments this is sufficient.
    """

    def __init__(self, max_calls: int, period: float) -> None:
        self._max = max_calls
        self._period = period
        self._log: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Record attempt. Returns True if within limit, False if exceeded."""
        now = time.monotonic()
        cutoff = now - self._period
        log = self._log[key]
        while log and log[0] < cutoff:
            log.popleft()
        if len(log) >= self._max:
            return False
        log.append(now)
        return True

    def require(self, key: str) -> None:
        """Raise HTTP 429 if rate limit is exceeded."""
        if not self.allow(key):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
