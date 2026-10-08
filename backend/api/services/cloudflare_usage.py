"""Today's Cloudflare Workers + Pages Functions request count, for the Monitor.

The Workers Free plan allows 100,000 requests per account per UTC day, shared
by Workers and Pages Functions (docs/guides/cloudflare-pages.md). Both datasets
come from the GraphQL Analytics API; each is queried on its own so one schema
or permission problem leaves the other number usable.

Results are cached for a few minutes: the Monitor polls, the analytics API is
itself delayed by minutes, and the owner should not be able to turn a refresh
button into an API flood.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

LOGGER = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
FREE_DAILY_REQUESTS = 100_000
CACHE_SECONDS = 300.0

_WORKERS_QUERY = """
query ($account: string!, $start: Time!, $end: Time!) {
  viewer {
    accounts(filter: {accountTag: $account}) {
      workersInvocationsAdaptive(
        limit: 1000
        filter: {datetime_geq: $start, datetime_lt: $end}
      ) {
        sum { requests }
        dimensions { scriptName }
      }
    }
  }
}
"""

_PAGES_QUERY = """
query ($account: string!, $start: Time!, $end: Time!) {
  viewer {
    accounts(filter: {accountTag: $account}) {
      pagesFunctionsInvocationsAdaptiveGroups(
        limit: 1000
        filter: {datetime_geq: $start, datetime_lt: $end}
      ) {
        sum { requests }
      }
    }
  }
}
"""


@dataclass(slots=True)
class CloudflareUsage:
    configured: bool
    limit: int = FREE_DAILY_REQUESTS
    day_start: str | None = None  # ISO, 00:00 UTC
    reset_at: str | None = None  # ISO, next 00:00 UTC (08:00 Taiwan)
    workers_requests: int | None = None
    pages_requests: int | None = None
    total_requests: int | None = None
    errors: list[str] = field(default_factory=list)
    fetched_at: str | None = None


_cache: tuple[float, CloudflareUsage] | None = None
_lock = asyncio.Lock()


def _sum_requests(rows: object) -> int:
    total = 0
    if isinstance(rows, list):
        for row in rows:
            requests = (row or {}).get("sum", {}).get("requests")
            if isinstance(requests, int | float):
                total += int(requests)
    return total


async def _query(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    dataset: str,
    variables: dict[str, str],
) -> tuple[int | None, str | None]:
    try:
        response = await client.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            return None, f"{dataset}: HTTP {response.status_code}"
        payload = response.json()
        if payload.get("errors"):
            message = str(payload["errors"][0].get("message", "unknown error"))
            return None, f"{dataset}: {message[:200]}"
        accounts = (payload.get("data") or {}).get("viewer", {}).get("accounts") or []
        if not accounts:
            return None, f"{dataset}: account not visible to this token"
        return _sum_requests(accounts[0].get(dataset)), None
    except Exception as exc:
        LOGGER.warning("Cloudflare %s query failed: %s", dataset, exc)
        return None, f"{dataset}: {type(exc).__name__}"


async def fetch_usage(account_id: str, api_token: str) -> CloudflareUsage:
    """Today's (UTC) usage; cached. Missing config is a state, not an error."""
    global _cache
    if not account_id or not api_token:
        return CloudflareUsage(configured=False)

    async with _lock:
        if _cache is not None and time.monotonic() - _cache[0] < CACHE_SECONDS:
            return _cache[1]

        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        variables = {
            "account": account_id,
            "start": day_start.isoformat().replace("+00:00", "Z"),
            "end": now.isoformat().replace("+00:00", "Z"),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            (workers, workers_error), (pages, pages_error) = await asyncio.gather(
                _query(client, api_token, _WORKERS_QUERY, "workersInvocationsAdaptive", variables),
                _query(
                    client,
                    api_token,
                    _PAGES_QUERY,
                    "pagesFunctionsInvocationsAdaptiveGroups",
                    variables,
                ),
            )

        known = [n for n in (workers, pages) if n is not None]
        usage = CloudflareUsage(
            configured=True,
            day_start=day_start.isoformat(),
            reset_at=(day_start + timedelta(days=1)).isoformat(),
            workers_requests=workers,
            pages_requests=pages,
            total_requests=sum(known) if known else None,
            errors=[e for e in (workers_error, pages_error) if e],
            fetched_at=now.isoformat(),
        )
        _cache = (time.monotonic(), usage)
        return usage


def clear_cache() -> None:
    global _cache
    _cache = None
