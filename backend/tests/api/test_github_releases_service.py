"""GitHub releases cache, revalidation, and stale-fallback contracts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from services.github_releases import (
    GitHubReleasesAuthError,
    GitHubReleasesClient,
    GitHubReleasesNotFoundError,
    GitHubReleasesTimeoutError,
    GitHubReleasesUpstreamError,
)

_PAYLOAD = [
    {
        "id": 1,
        "tag_name": "v1.2.3",
        "name": "Release 1.2.3",
        "body": "Changelog",
        "published_at": "2024-01-01T00:00:00Z",
        "prerelease": False,
        "draft": False,
    },
    {
        "id": 2,
        "tag_name": "v1.2.4-draft",
        "name": "Draft",
        "body": None,
        "published_at": "2024-01-02T00:00:00Z",
        "prerelease": False,
        "draft": True,
    },
]


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.wall_now = 1_000.0

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.wall_now

    def advance(self, seconds: float) -> None:
        self.now += seconds
        self.wall_now += seconds


def _response(status: int, payload=None, **headers: str) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.headers = httpx.Headers(headers)
    response.json.return_value = [] if payload is None else payload
    return response


def _client(
    raw: MagicMock,
    clock: _Clock,
    *,
    fresh_ttl: float = 10.0,
    stale_ttl: float = 60.0,
) -> GitHubReleasesClient:
    return GitHubReleasesClient(
        raw,
        fresh_ttl_seconds=fresh_ttl,
        stale_ttl_seconds=stale_ttl,
        monotonic=clock.monotonic,
        wall_clock=clock.time,
    )


@pytest.mark.asyncio
async def test_fresh_cache_avoids_a_second_github_request() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(return_value=_response(200, _PAYLOAD, ETag='"v1"'))
    raw.aclose = AsyncMock()
    client = _client(raw, clock)

    first = await client.get_releases("token")
    second = await client.get_releases("token")

    assert first == second
    assert [release.tag_name for release in first] == ["v1.2.3"]
    raw.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_cache_misses_use_single_flight() -> None:
    clock = _Clock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def get(*_args: object, **_kwargs: object) -> MagicMock:
        started.set()
        await release.wait()
        return _response(200, _PAYLOAD)

    raw = MagicMock()
    raw.get = AsyncMock(side_effect=get)
    raw.aclose = AsyncMock()
    client = _client(raw, clock)
    first = asyncio.create_task(client.get_releases("token"))
    second = asyncio.create_task(client.get_releases("token"))
    await started.wait()
    await asyncio.sleep(0)

    raw.get.assert_awaited_once()
    release.set()
    assert await first == await second


@pytest.mark.asyncio
async def test_etag_304_extends_freshness_without_replacing_payload() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(
        side_effect=[
            _response(200, _PAYLOAD, ETag='"v1"'),
            _response(304, None, ETag='"v1"'),
        ]
    )
    raw.aclose = AsyncMock()
    client = _client(raw, clock)

    first = await client.get_releases("token")
    clock.advance(10.0)
    second = await client.get_releases("token")
    third = await client.get_releases("token")

    assert first == second == third
    assert raw.get.await_count == 2
    assert raw.get.await_args_list[1].kwargs["headers"]["If-None-Match"] == '"v1"'


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [httpx.TimeoutException("timeout"), _response(503)])
async def test_transient_failure_returns_last_known_good(failure: object) -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(side_effect=[_response(200, _PAYLOAD), failure])
    raw.aclose = AsyncMock()
    client = _client(raw, clock)
    expected = await client.get_releases("token")
    clock.advance(10.0)

    assert await client.get_releases("token") == expected


@pytest.mark.asyncio
async def test_timeout_without_stale_data_is_explicit() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    raw.aclose = AsyncMock()
    client = _client(raw, clock)

    with pytest.raises(GitHubReleasesTimeoutError):
        await client.get_releases("token")


@pytest.mark.asyncio
async def test_429_defers_refresh_and_serves_stale_without_another_request() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(
        side_effect=[
            _response(200, _PAYLOAD),
            _response(429, None, **{"Retry-After": "20"}),
        ]
    )
    raw.aclose = AsyncMock()
    client = _client(raw, clock)
    expected = await client.get_releases("token")
    clock.advance(10.0)

    assert await client.get_releases("token") == expected
    assert await client.get_releases("token") == expected
    assert raw.get.await_count == 2


@pytest.mark.asyncio
async def test_rate_limit_reset_epoch_is_honored_for_403() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(
        side_effect=[
            _response(200, _PAYLOAD),
            _response(
                403,
                None,
                **{"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1030"},
            ),
        ]
    )
    raw.aclose = AsyncMock()
    client = _client(raw, clock)
    expected = await client.get_releases("token")
    clock.advance(10.0)

    assert await client.get_releases("token") == expected
    assert await client.get_releases("token") == expected
    assert raw.get.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, GitHubReleasesAuthError),
        (403, GitHubReleasesAuthError),
        (404, GitHubReleasesNotFoundError),
    ],
)
async def test_deterministic_errors_are_not_hidden_by_stale_data(
    status: int,
    error: type[Exception],
) -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(side_effect=[_response(200, _PAYLOAD), _response(status)])
    raw.aclose = AsyncMock()
    client = _client(raw, clock)
    await client.get_releases("token")
    clock.advance(10.0)

    with pytest.raises(error):
        await client.get_releases("token")


@pytest.mark.asyncio
async def test_auth_error_invalidates_stale_snapshot() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(
        side_effect=[
            _response(200, _PAYLOAD),
            _response(401),
            _response(500),
        ]
    )
    raw.aclose = AsyncMock()
    client = _client(raw, clock)
    await client.get_releases("token")
    clock.advance(10.0)

    with pytest.raises(GitHubReleasesAuthError):
        await client.get_releases("bad-token")
    with pytest.raises(GitHubReleasesUpstreamError):
        await client.get_releases("token")


@pytest.mark.asyncio
async def test_malformed_success_payload_is_not_cached() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(
        side_effect=[
            _response(200, ["not-an-object"]),
            _response(200, _PAYLOAD),
        ]
    )
    raw.aclose = AsyncMock()
    client = _client(raw, clock)

    with pytest.raises(GitHubReleasesUpstreamError):
        await client.get_releases("token")
    assert [release.tag_name for release in await client.get_releases("token")] == ["v1.2.3"]
    assert raw.get.await_count == 2


@pytest.mark.asyncio
async def test_expired_stale_data_does_not_mask_upstream_failure() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock(side_effect=[_response(200, _PAYLOAD), _response(500)])
    raw.aclose = AsyncMock()
    client = _client(raw, clock, fresh_ttl=10.0, stale_ttl=20.0)
    await client.get_releases("token")
    clock.advance(20.0)

    with pytest.raises(GitHubReleasesUpstreamError) as exc_info:
        await client.get_releases("token")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_close_closes_shared_http_client() -> None:
    clock = _Clock()
    raw = MagicMock()
    raw.get = AsyncMock()
    raw.aclose = AsyncMock()
    client = _client(raw, clock)

    await client.aclose()

    raw.aclose.assert_awaited_once()
