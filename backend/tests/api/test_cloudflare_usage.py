"""Cloudflare daily-usage service: per-dataset isolation, caching, missing config."""

from __future__ import annotations

import json
from collections.abc import Iterator
from unittest.mock import patch

import httpx
import pytest

from services import cloudflare_usage


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    cloudflare_usage.clear_cache()
    yield
    cloudflare_usage.clear_cache()


def _patched(handler):
    real = httpx.AsyncClient
    return patch.object(
        cloudflare_usage.httpx,
        "AsyncClient",
        side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


def _rows(dataset: str, *requests: int) -> dict:
    rows = [{"sum": {"requests": n}} for n in requests]
    return {"data": {"viewer": {"accounts": [{dataset: rows}]}}}


@pytest.mark.asyncio
async def test_unconfigured_is_a_state_not_an_error() -> None:
    usage = await cloudflare_usage.fetch_usage("", "token")
    assert usage.configured is False
    assert usage.errors == []


@pytest.mark.asyncio
async def test_sums_both_datasets_and_sends_the_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        query = json.loads(request.content)["query"]
        if "workersInvocationsAdaptive" in query:
            return httpx.Response(200, json=_rows("workersInvocationsAdaptive", 10, 5))
        return httpx.Response(200, json=_rows("pagesFunctionsInvocationsAdaptiveGroups", 100))

    with _patched(handler):
        usage = await cloudflare_usage.fetch_usage("acct", "secret-token")

    assert usage.workers_requests == 15
    assert usage.pages_requests == 100
    assert usage.total_requests == 115
    assert usage.errors == []
    assert usage.reset_at is not None and usage.reset_at.endswith("00:00:00+00:00")
    assert all(r.headers["Authorization"] == "Bearer secret-token" for r in seen)
    variables = json.loads(seen[0].content)["variables"]
    assert variables["account"] == "acct"
    assert variables["start"].endswith("T00:00:00Z")


@pytest.mark.asyncio
async def test_one_failing_dataset_leaves_the_other_usable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "workersInvocationsAdaptive" in json.loads(request.content)["query"]:
            return httpx.Response(200, json=_rows("workersInvocationsAdaptive", 7))
        return httpx.Response(200, json={"errors": [{"message": "unknown field"}], "data": None})

    with _patched(handler):
        usage = await cloudflare_usage.fetch_usage("acct", "t")

    assert usage.workers_requests == 7
    assert usage.pages_requests is None
    assert usage.total_requests == 7
    assert usage.errors == ["pagesFunctionsInvocationsAdaptiveGroups: unknown field"]


@pytest.mark.asyncio
async def test_results_are_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403)

    with _patched(handler):
        first = await cloudflare_usage.fetch_usage("acct", "t")
        second = await cloudflare_usage.fetch_usage("acct", "t")

    assert first is second
    assert calls == 2  # one per dataset, once
    assert first.total_requests is None
    assert first.errors == [
        "workersInvocationsAdaptive: HTTP 403",
        "pagesFunctionsInvocationsAdaptiveGroups: HTTP 403",
    ]
