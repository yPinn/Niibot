"""Shared retry helpers used by Discord and Twitch bot launchers."""

from __future__ import annotations

import time


def format_duration(seconds: float) -> str:
    """Format seconds into a compact human-readable string (e.g. 2h30m, 5m10s, 45s)."""
    s = int(seconds)
    if s >= 3600:
        h, remainder = divmod(s, 3600)
        m = remainder // 60
        return f"{h}h{m}m" if m else f"{h}h"
    if s >= 60:
        m, sec = divmod(s, 60)
        return f"{m}m{sec}s" if sec else f"{m}m"
    return f"{s}s"


def parse_retry_after(exc: Exception, fallback: float = 5.0) -> float:
    """Extract retry-after seconds from a rate-limit exception.

    Priority:
      1. ``exc.retry_after`` attribute (parsed by discord.py / twitchio)
      2. ``Retry-After`` / ``retry-after`` / ``retry_after`` response header
      3. ``Ratelimit-Reset`` absolute epoch response header
      4. ``fallback`` value
    """
    retry_after: float | None = None

    if hasattr(exc, "retry_after"):
        try:
            val = float(exc.retry_after)  # type: ignore[attr-defined]
            if val > 0:
                retry_after = val
        except (ValueError, TypeError):
            pass

    if retry_after is None:
        resp = getattr(exc, "response", None)
        if resp is not None:
            headers = getattr(resp, "headers", {})
            for key in ("Retry-After", "retry-after", "retry_after"):
                if key in headers:
                    try:
                        val = float(headers[key])
                        if val > 0:
                            retry_after = val
                    except (ValueError, TypeError):
                        pass
                    break

            if retry_after is None:
                for key in ("Ratelimit-Reset", "ratelimit-reset", "ratelimit_reset"):
                    if key in headers:
                        try:
                            val = float(headers[key]) - time.time()
                            if val > 0:
                                retry_after = val
                        except (ValueError, TypeError):
                            pass
                        break

    return retry_after if retry_after is not None else fallback
