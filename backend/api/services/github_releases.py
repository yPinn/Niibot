"""Cached GitHub releases client with conditional revalidation."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

_GITHUB_REPO = "yPinn/Niibot"
_GITHUB_API_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases"


class GithubRelease(BaseModel):
    id: int
    tag_name: str
    name: str | None = None
    body: str | None = None
    published_at: str
    prerelease: bool
    draft: bool


class GitHubReleasesError(RuntimeError):
    """Base class for explicit upstream failure semantics."""


class GitHubReleasesNotFoundError(GitHubReleasesError):
    pass


class GitHubReleasesAuthError(GitHubReleasesError):
    pass


class GitHubReleasesTimeoutError(GitHubReleasesError):
    pass


class GitHubReleasesUpstreamError(GitHubReleasesError):
    def __init__(self, status_code: int | None = None) -> None:
        super().__init__(f"GitHub releases upstream failed ({status_code or 'unknown'})")
        self.status_code = status_code


class GitHubReleasesClient:
    """Reuse one HTTP client and one process-local release snapshot."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        fresh_ttl_seconds: float = 300.0,
        stale_ttl_seconds: float = 3_600.0,
        max_defer_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if fresh_ttl_seconds <= 0:
            raise ValueError("fresh_ttl_seconds must be positive")
        if stale_ttl_seconds <= fresh_ttl_seconds:
            raise ValueError("stale_ttl_seconds must exceed fresh_ttl_seconds")
        if max_defer_seconds <= 0:
            raise ValueError("max_defer_seconds must be positive")
        self._client = client
        self._fresh_ttl_seconds = fresh_ttl_seconds
        self._stale_ttl_seconds = stale_ttl_seconds
        self._max_defer_seconds = max_defer_seconds
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._releases: list[GithubRelease] | None = None
        self._etag: str | None = None
        self._fresh_until = 0.0
        self._stale_until = 0.0
        self._blocked_until = 0.0
        self._inflight: asyncio.Task[list[GithubRelease]] | None = None
        self._closed = False

    async def get_releases(self, token: str = "") -> list[GithubRelease]:
        if self._closed:
            raise RuntimeError("GitHub releases client is closed")
        now = self._monotonic()
        if self._releases is not None and now < self._fresh_until:
            return list(self._releases)
        if now < self._blocked_until:
            return self._stale_or_raise(GitHubReleasesUpstreamError(429))

        task = self._inflight
        if task is None:
            task = asyncio.create_task(self._refresh(token))
            self._inflight = task
        try:
            return list(await asyncio.shield(task))
        finally:
            if self._inflight is task and task.done():
                self._inflight = None

    async def _refresh(self, token: str) -> list[GithubRelease]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self._etag:
            headers["If-None-Match"] = self._etag

        try:
            response = await self._client.get(
                _GITHUB_API_URL,
                params={"per_page": "30"},
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            return self._stale_or_raise(GitHubReleasesTimeoutError(), cause=exc)
        except httpx.RequestError as exc:
            return self._stale_or_raise(GitHubReleasesUpstreamError(), cause=exc)

        status = response.status_code
        if status == 304:
            if self._releases is None:
                raise GitHubReleasesUpstreamError(304)
            self._mark_fresh()
            self._etag = response.headers.get("etag") or self._etag
            return list(self._releases)

        if status == 200:
            try:
                payload = response.json()
                if not isinstance(payload, list):
                    raise TypeError("GitHub releases payload is not a list")
                if any(not isinstance(item, dict) for item in payload):
                    raise TypeError("GitHub release entry is not an object")
                releases = [
                    GithubRelease.model_validate(item) for item in payload if not item.get("draft")
                ]
            except (TypeError, ValueError, ValidationError) as exc:
                return self._stale_or_raise(GitHubReleasesUpstreamError(200), cause=exc)
            self._releases = releases
            self._etag = response.headers.get("etag")
            self._mark_fresh()
            return list(releases)

        if status == 404:
            self._invalidate()
            raise GitHubReleasesNotFoundError
        if status in {401, 403} and not self._is_rate_limited(status, response.headers):
            self._invalidate()
            raise GitHubReleasesAuthError
        if self._is_rate_limited(status, response.headers):
            self._blocked_until = max(
                self._blocked_until,
                self._monotonic() + self._retry_delay(response.headers),
            )
            return self._stale_or_raise(GitHubReleasesUpstreamError(status))
        if status >= 500:
            return self._stale_or_raise(GitHubReleasesUpstreamError(status))
        raise GitHubReleasesUpstreamError(status)

    def _mark_fresh(self) -> None:
        now = self._monotonic()
        self._fresh_until = now + self._fresh_ttl_seconds
        self._stale_until = now + self._stale_ttl_seconds

    def _invalidate(self) -> None:
        self._releases = None
        self._etag = None
        self._fresh_until = 0.0
        self._stale_until = 0.0

    def _stale_or_raise[E: Exception](
        self,
        error: E,
        *,
        cause: BaseException | None = None,
    ) -> list[GithubRelease]:
        if self._releases is not None and self._monotonic() < self._stale_until:
            return list(self._releases)
        if cause is not None:
            raise error from cause
        raise error

    @staticmethod
    def _is_rate_limited(status: int, headers: Mapping[str, Any]) -> bool:
        if status == 429:
            return True
        if status != 403:
            return False
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        return normalized.get("x-ratelimit-remaining") == "0" or any(
            key in normalized for key in ("retry-after", "x-ratelimit-reset")
        )

    def _retry_delay(self, headers: Mapping[str, Any]) -> float:
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        retry_after = normalized.get("retry-after")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(retry_after)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    delay = (
                        parsed.timestamp()
                        - datetime.fromtimestamp(
                            self._wall_clock(),
                            tz=UTC,
                        ).timestamp()
                    )
                except (TypeError, ValueError, OverflowError):
                    delay = 0.0
            if delay > 0:
                return min(delay, self._max_defer_seconds)

        reset = normalized.get("x-ratelimit-reset")
        if reset:
            try:
                delay = float(reset) - self._wall_clock()
                if delay > 0:
                    return min(delay, self._max_defer_seconds)
            except ValueError:
                pass
        return min(5.0, self._max_defer_seconds)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()
