"""Reusable PostgreSQL LISTEN/NOTIFY helper with auto-reconnect.

Uses dedicated connections (asyncpg.connect) instead of borrowing from
the shared pool, so LISTEN channels don't consume pool slots.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import asyncpg

LOGGER = logging.getLogger("PgListener")


async def pg_listen(
    dsn: str,
    channel: str,
    handler: Callable[..., Coroutine[Any, Any, None]],
    *,
    keepalive_interval: int = 15,
    reconnect_delay: int = 10,
) -> None:
    """Listen on a PostgreSQL NOTIFY channel with auto-reconnect.

    Creates a dedicated connection (not from the pool) so LISTEN channels
    don't consume pool capacity.

    Args:
        dsn: PostgreSQL connection string.
        channel: PostgreSQL NOTIFY channel name.
        handler: Async callback ``(connection, pid, channel, payload) -> None``.
        keepalive_interval: Seconds between keepalive pings (default 15).
            Shorter than Supavisor's client_heartbeat_interval to prevent
            the proxy from marking LISTEN connections as dead.
        reconnect_delay: Seconds to wait before reconnect after error.
    """
    while True:
        connection: asyncpg.Connection | None = None
        try:
            connection = await asyncpg.connect(dsn, ssl="require")
            await connection.add_listener(channel, handler)
            LOGGER.info(f"PostgreSQL LISTEN active on '{channel}' channel")

            try:
                while True:
                    await asyncio.sleep(keepalive_interval)
                    await connection.execute("SELECT 1")
            except asyncio.CancelledError:
                LOGGER.info(f"PostgreSQL LISTEN '{channel}' shutting down...")
                raise
            finally:
                try:
                    await connection.remove_listener(channel, handler)
                except Exception:
                    pass
                try:
                    await connection.close()
                except Exception:
                    pass
                connection = None

        except asyncio.CancelledError:
            break
        except Exception as e:
            LOGGER.error(f"Error in pg_listen('{channel}'): {e}")
            LOGGER.warning(
                f"Reconnecting to PostgreSQL LISTEN '{channel}' in {reconnect_delay}s..."
            )
            if connection is not None:
                try:
                    await connection.remove_listener(channel, handler)
                except Exception:
                    pass
                try:
                    await connection.close()
                except Exception:
                    pass
                connection = None
            try:
                await asyncio.sleep(reconnect_delay)
            except asyncio.CancelledError:
                break
