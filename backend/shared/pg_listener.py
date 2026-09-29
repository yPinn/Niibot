"""Reusable PostgreSQL LISTEN/NOTIFY helper with auto-reconnect.

Uses dedicated connections (asyncpg.connect) instead of borrowing from
the shared pool, so LISTEN channels don't consume pool slots.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

import asyncpg

LOGGER: logging.Logger = logging.getLogger(__name__)


async def pg_listen(
    dsn: str,
    channel: str,
    handler: Callable[..., Coroutine[Any, Any, None]],
    *,
    keepalive_interval: int = 60,
    reconnect_delay: int = 10,
    on_connected: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> None:
    """Listen on a PostgreSQL NOTIFY channel with auto-reconnect.

    Creates a dedicated connection (not from the pool) so LISTEN channels
    don't consume pool capacity.

    Args:
        dsn: PostgreSQL connection string.
        channel: PostgreSQL NOTIFY channel name.
        handler: Async callback ``(connection, pid, channel, payload) -> None``.
        keepalive_interval: Seconds between keepalive pings (default 60).
            Prevents the server from closing the idle LISTEN connection.
        reconnect_delay: Seconds to wait before reconnect after error.
        on_connected: Optional catch-up callback invoked after every successful
            LISTEN registration, including reconnects. Callback failures are
            logged without dropping the listener connection.
    """
    await pg_listen_many(
        dsn,
        {channel: handler},
        keepalive_interval=keepalive_interval,
        reconnect_delay=reconnect_delay,
        on_connected=on_connected,
    )


async def pg_listen_many(
    dsn: str,
    handlers: Mapping[str, Callable[..., Coroutine[Any, Any, None]]],
    *,
    keepalive_interval: int = 60,
    reconnect_delay: int = 10,
    on_connected: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> None:
    """Listen on multiple channels through one auto-reconnecting connection."""
    if not handlers:
        raise ValueError("at least one PostgreSQL LISTEN channel is required")

    channel_names = tuple(handlers)
    channel_label = ",".join(channel_names)
    while True:
        connection: asyncpg.Connection | None = None
        reconnect = True
        try:
            connection = await asyncpg.connect(dsn, ssl="prefer")
            for channel, handler in handlers.items():
                await connection.add_listener(channel, handler)
            LOGGER.info("PostgreSQL LISTEN active on '%s'", channel_label)
            if on_connected is not None:
                try:
                    await on_connected()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    LOGGER.exception(
                        "PostgreSQL LISTEN '%s' catch-up callback failed",
                        channel_label,
                    )

            while True:
                await asyncio.sleep(keepalive_interval)
                await connection.execute("SELECT 1")
        except asyncio.CancelledError:
            reconnect = False
            LOGGER.info("PostgreSQL LISTEN '%s' shutting down...", channel_label)
        except Exception as e:
            LOGGER.error(
                "Error in pg_listen_many('%s'): %s",
                channel_label,
                e,
                extra={
                    "code": "RUNTIME.LISTENER_DISCONNECTED",
                    "event_class": "persistent",
                    "notify_channel": channel_label,
                },
            )
            LOGGER.warning(
                "Reconnecting to PostgreSQL LISTEN '%s' in %ss...",
                channel_label,
                reconnect_delay,
            )
        finally:
            if connection is not None:
                for channel, handler in handlers.items():
                    try:
                        await connection.remove_listener(channel, handler)
                    except Exception:
                        pass
                try:
                    await connection.close()
                except Exception:
                    pass

        if not reconnect:
            break
        try:
            await asyncio.sleep(reconnect_delay)
        except asyncio.CancelledError:
            break
