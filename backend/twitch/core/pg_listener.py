"""Reusable PostgreSQL LISTEN/NOTIFY helper with auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import asyncpg

LOGGER = logging.getLogger("PgListener")


async def pg_listen(
    pool: asyncpg.Pool,
    channel: str,
    handler: Callable[..., Coroutine[Any, Any, None]],
    *,
    keepalive_interval: int = 60,
    reconnect_delay: int = 10,
) -> None:
    """Listen on a PostgreSQL NOTIFY channel with auto-reconnect.

    Args:
        pool: asyncpg connection pool.
        channel: PostgreSQL NOTIFY channel name.
        handler: Async callback ``(connection, pid, channel, payload) -> None``.
        keepalive_interval: Seconds between keepalive pings.
        reconnect_delay: Seconds to wait before reconnect after error.
    """
    while True:
        connection: asyncpg.Connection | None = None
        try:
            connection = await pool.acquire()
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
                await pool.release(connection)
                connection = None

        except asyncio.CancelledError:
            break
        except Exception as e:
            LOGGER.exception(f"Error in pg_listen('{channel}'): {e}")
            LOGGER.warning(
                f"Reconnecting to PostgreSQL LISTEN '{channel}' in {reconnect_delay}s..."
            )
            if connection is not None:
                try:
                    await connection.remove_listener(channel, handler)
                except Exception:
                    pass
                try:
                    await pool.release(connection)
                except Exception:
                    pass
            try:
                await asyncio.sleep(reconnect_delay)
            except asyncio.CancelledError:
                break
