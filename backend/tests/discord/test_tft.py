"""Concurrency contracts for Tactics.tools reads."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.cogs.tft import TftCog


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


def _player_response() -> MagicMock:
    data = {
        "props": {
            "pageProps": {
                "playerName": "Alice",
                "initialData": {
                    "playerInfo": {
                        "rankedLeague": ["MASTER", 100],
                        "localRank": [0, 0.01],
                        "matches": [],
                    }
                },
            }
        }
    }
    response = MagicMock()
    response.status_code = 200
    response.text = (
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    )
    return response


def _cog(clock: _Clock) -> TftCog:
    cog = object.__new__(TftCog)
    cog._last_request = 0.0
    cog._cache = None
    cog._cache_time = 0.0
    cog._client = MagicMock()
    cog._user_agents = ["test-agent"]
    cog._request_lock = asyncio.Lock()
    cog._leaderboard_lock = asyncio.Lock()
    cog._clock = clock
    cog._sleep = clock.sleep
    return cog


@pytest.mark.asyncio
async def test_concurrent_player_fetches_are_serialized_and_spaced() -> None:
    clock = _Clock()
    cog = _cog(clock)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    request_times: list[float] = []

    async def get(*_args: object, **_kwargs: object) -> MagicMock:
        request_times.append(clock.now)
        if len(request_times) == 1:
            first_started.set()
            await release_first.wait()
        return _player_response()

    cog._client.get = AsyncMock(side_effect=get)
    with patch("discord.cogs.tft.random.uniform", return_value=0.0):
        first = asyncio.create_task(cog._fetch_player_data("Alice", "TW1"))
        await first_started.wait()
        second = asyncio.create_task(cog._fetch_player_data("Bob", "TW2"))
        await asyncio.sleep(0)
        assert cog._client.get.await_count == 1

        release_first.set()
        await asyncio.gather(first, second)

    assert request_times == [100.0, 103.0]


@pytest.mark.asyncio
async def test_concurrent_leaderboard_misses_share_the_first_result() -> None:
    clock = _Clock()
    cog = _cog(clock)
    started = asyncio.Event()
    release = asyncio.Event()
    leaderboard = {"entries": [], "thresholds": [1000, 500]}
    response = MagicMock()
    response.status_code = 200
    response.text = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"pageProps": {"data": leaderboard}}})
        + "</script>"
    )

    async def get(*_args: object, **_kwargs: object) -> MagicMock:
        started.set()
        await release.wait()
        return response

    cog._client.get = AsyncMock(side_effect=get)
    with patch("discord.cogs.tft.random.uniform", return_value=0.0):
        first = asyncio.create_task(cog.get_leaderboard_data())
        await started.wait()
        second = asyncio.create_task(cog.get_leaderboard_data())
        await asyncio.sleep(0)
        release.set()
        assert await asyncio.gather(first, second) == [leaderboard, leaderboard]

    cog._client.get.assert_awaited_once()
