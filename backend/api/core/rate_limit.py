"""In-process sliding-window rate limiter — zero external dependency."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from shared import rate_limits
from shared.rate_limits import RateLimitSnapshot

# Behind Cloudflare Tunnel the socket peer is always the Docker gateway, so the
# caller has to come from headers — only ones Cloudflare itself controls
# (measured on staging; see docs/guides/cloudflare-pages.md):
# - CF-Connecting-IP: a client-sent value is refused (error 1000). Real caller on
#   the direct tunnel host; the shared Workers egress IP when Pages proxies.
# - CF-Worker: names the zone of the Worker that made the subrequest; stripped when
#   a client sends it. Ours means the Pages Function wrote CLIENT_IP_HEADER from its
#   own incoming CF-Connecting-IP. Another account's Worker carries its own zone.
# X-Forwarded-For and True-Client-IP keep client-supplied values: never trusted.
PAGES_WORKER_ZONE = "niibot.pages.dev"
CLIENT_IP_HEADER = "x-niibot-client-ip"


def client_ip(request: Request) -> str:
    """The caller's IP for per-client keys (rate limits, telemetry hashes)."""
    headers = request.headers
    if headers.get("cf-worker") == PAGES_WORKER_ZONE:
        forwarded = headers.get(CLIENT_IP_HEADER)
        if forwarded:
            return forwarded
    connecting = headers.get("cf-connecting-ip")
    if connecting:
        return connecting
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window counter per arbitrary string key.

    In-process only: resets on restart and is not multi-instance safe.
    For single-process deployments this is sufficient.
    """

    _SWEEP_INTERVAL = 500  # calls between idle-key eviction sweeps

    def __init__(self, max_calls: int, period: float, *, name: str | None = None) -> None:
        self._max = max_calls
        self._period = period
        self._log: dict[str, deque[float]] = defaultdict(deque)
        self._calls_since_sweep = 0
        self.name = name
        self._allowed = 0
        self._rejected = 0
        self._last_rejected_at: float | None = None
        # Named limiters show up in /status (admin Monitor → 限流).
        if name:
            rate_limits.register(f"limiter:{name}", lambda: [self.snapshot()])

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
            self._allowed += 1
        else:
            self._rejected += 1
            self._last_rejected_at = time.time()
        self._maybe_sweep(now)
        return allowed

    def snapshot(self) -> RateLimitSnapshot:
        """Current-window usage. Read-only: expired entries are skipped, not pruned."""
        cutoff = time.monotonic() - self._period
        counts = [sum(1 for t in log if t >= cutoff) for log in list(self._log.values())]
        active = [c for c in counts if c]
        return {
            "name": self.name or "unnamed",
            "group": "inbound",
            "limit": self._max,
            "window_seconds": self._period,
            "used": max(active, default=0),
            "keys": len(active),
            "allowed": self._allowed,
            "rejected": self._rejected,
            "last_rejected_at": self._last_rejected_at,
        }

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
