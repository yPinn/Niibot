"""Request / command-scoped log context.

A thin wrapper over ``structlog.contextvars`` so call sites don't import
structlog directly and there is one place that lists the keys we bind:

    request_id, http_method, http_path   — API middleware (per request)
    user_id, channel_id                  — API auth dependencies
    channel, channel_id, chatter, guild_id, command
                                         — bot dispatch (per message / command)

``merge_contextvars`` in ``logging_setup`` copies whatever is bound into
every log line emitted while the binding is active.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from structlog.contextvars import (
    bind_contextvars,
    bound_contextvars,
    clear_contextvars,
    get_contextvars,
)

__all__ = [
    "bind_log_context",
    "bound_log_context",
    "clear_log_context",
    "get_request_id",
]


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def bind_log_context(**values: Any) -> None:
    """Bind keys for the rest of the current context. ``None`` values skipped."""
    clean = _drop_none(values)
    if clean:
        bind_contextvars(**clean)


def clear_log_context() -> None:
    clear_contextvars()


@contextmanager
def bound_log_context(**values: Any) -> Iterator[None]:
    """Bind keys for the duration of the ``with`` block only."""
    with bound_contextvars(**_drop_none(values)):
        yield


def get_request_id() -> str | None:
    rid = get_contextvars().get("request_id")
    return rid if isinstance(rid, str) else None
