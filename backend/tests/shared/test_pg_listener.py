"""Durability contracts for the PostgreSQL LISTEN helper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from shared.pg_listener import pg_listen, pg_listen_many


@pytest.mark.asyncio
async def test_on_connected_runs_again_after_listener_reconnect() -> None:
    first = AsyncMock()
    first.execute.side_effect = RuntimeError("connection dropped")
    second = AsyncMock()
    on_connected = AsyncMock()
    handler = AsyncMock()

    with (
        patch("shared.pg_listener.asyncpg.connect", new=AsyncMock(side_effect=[first, second])),
        patch(
            "shared.pg_listener.asyncio.sleep",
            new=AsyncMock(side_effect=[None, None, asyncio.CancelledError]),
        ),
    ):
        await pg_listen(
            "postgresql://test",
            "token_reauth",
            handler,
            on_connected=on_connected,
        )

    assert on_connected.await_count == 2
    assert first.add_listener.await_count == 1
    assert second.add_listener.await_count == 1


@pytest.mark.asyncio
async def test_many_channels_share_one_reconnecting_connection() -> None:
    first = AsyncMock()
    first.execute.side_effect = RuntimeError("connection dropped")
    second = AsyncMock()
    handlers = {
        "new_token": AsyncMock(),
        "token_reauth": AsyncMock(),
    }
    on_connected = AsyncMock()

    with (
        patch("shared.pg_listener.asyncpg.connect", new=AsyncMock(side_effect=[first, second])),
        patch(
            "shared.pg_listener.asyncio.sleep",
            new=AsyncMock(side_effect=[None, None, asyncio.CancelledError]),
        ),
    ):
        await pg_listen_many(
            "postgresql://test",
            handlers,
            on_connected=on_connected,
        )

    assert on_connected.await_count == 2
    assert first.add_listener.await_count == len(handlers)
    assert second.add_listener.await_count == len(handlers)
    assert {call.args[0] for call in first.add_listener.await_args_list} == set(handlers)


@pytest.mark.asyncio
async def test_cancellation_during_catch_up_closes_listener_connection() -> None:
    connection = AsyncMock()

    with patch(
        "shared.pg_listener.asyncpg.connect",
        new=AsyncMock(return_value=connection),
    ):
        await pg_listen(
            "postgresql://test",
            "token_reauth",
            AsyncMock(),
            on_connected=AsyncMock(side_effect=asyncio.CancelledError),
        )

    connection.close.assert_awaited_once()
