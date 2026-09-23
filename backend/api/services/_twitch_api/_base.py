"""Shared HTTP plumbing for TwitchAPIClient.

Owns the httpx client lifecycle, the app-access-token cache, the Helix GET
helper, and cursor pagination — everything the per-domain mixins build on.
"""

import asyncio
import logging
import re
import time

import httpx

from shared.twitch_egress import TwitchEgressCoordinator, credential_bucket_key
from shared.twitch_scopes import BROADCASTER_SCOPES as _BROADCASTER_SCOPES

LOGGER: logging.Logger = logging.getLogger(__name__)

# Pre-compiled regex for duration parsing
_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")

HELIX_BASE = "https://api.twitch.tv/helix"
OAUTH_BASE = "https://id.twitch.tv/oauth2"


class _TwitchAPIBase:
    """HTTP client lifecycle, app-token cache, and Helix request helpers.

    Manages a shared httpx client for connection reuse and caches
    the app access token to avoid redundant token requests.
    """

    BROADCASTER_SCOPES = _BROADCASTER_SCOPES

    def __init__(self, client_id: str, client_secret: str, api_url: str):
        if not client_id or not client_secret:
            raise ValueError("Twitch client_id and client_secret are required")

        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = api_url

        # Shared HTTP client — reuses TCP connections across requests
        self._http = httpx.AsyncClient(timeout=10.0)

        # App token cache
        self._app_token: str | None = None
        self._app_token_expires_at: float = 0.0
        self._app_token_lock = asyncio.Lock()
        self._egress = TwitchEgressCoordinator()

    async def close(self) -> None:
        """Close the shared HTTP client. Call on app shutdown."""
        await self._http.aclose()
        await self._egress.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _app_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Client-Id": self.client_id}

    async def _ensure_app_token(self) -> str | None:
        """Return a cached app access token, refreshing only when expired."""
        now = time.monotonic()
        if self._app_token and now < self._app_token_expires_at:
            return self._app_token

        async with self._app_token_lock:
            # Double-check after acquiring lock
            now = time.monotonic()
            if self._app_token and now < self._app_token_expires_at:
                return self._app_token

            try:
                response = await self._http.post(
                    f"{OAUTH_BASE}/token",
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials",
                    },
                )
                if response.status_code != 200:
                    LOGGER.error(f"Failed to get app token: {response.status_code}")
                    return None

                data = response.json()
                self._app_token = data.get("access_token")
                # Twitch returns expires_in in seconds; refresh 5 min early
                expires_in = data.get("expires_in", 0)
                self._app_token_expires_at = now + max(expires_in - 300, 0)
                return self._app_token

            except Exception:
                LOGGER.exception("Error getting app access token")
                return None

    async def _helix_get(
        self,
        path: str,
        params: dict | None = None,
        *,
        token: str | None = None,
    ) -> httpx.Response | None:
        """GET request to Helix API. Uses app token when *token* is None."""
        if token is None:
            token = await self._ensure_app_token()
            if not token:
                return None
        bucket_key = credential_bucket_key(token)
        for attempt in range(2):
            await self._egress.acquire_helix(bucket_key)
            try:
                response = await self._http.get(
                    f"{HELIX_BASE}/{path}",
                    params=params,
                    headers=self._app_headers(token),
                )
            except Exception:
                LOGGER.exception("Helix GET /%s error", path)
                return None
            self._egress.observe_helix(
                bucket_key,
                status_code=response.status_code,
                headers=response.headers,
            )
            if response.status_code != 429 or attempt == 1:
                return response
        raise AssertionError("unreachable Helix retry state")

    async def _fetch_paginated(self, path: str, params: dict, *, token: str) -> list[dict]:
        """Fetch all pages from a cursor-paginated Helix endpoint."""
        results: list[dict] = []
        cursor: str | None = None
        while True:
            p = {**params, "first": 100}
            if cursor:
                p["after"] = cursor
            response = await self._helix_get(path, p, token=token)
            if not response or response.status_code != 200:
                body_hint = ""
                if response is not None:
                    try:
                        body_hint = response.json().get("message", "") or response.text[:200]
                    except Exception:
                        body_hint = response.text[:200]
                status_str = response.status_code if response else "no_response"
                LOGGER.warning(
                    "Paginated fetch of %s stopped: status=%s%s",
                    path,
                    status_str,
                    f" — {body_hint}" if body_hint else "",
                )
                break
            body = response.json()
            results.extend(body.get("data", []))
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return results

    @staticmethod
    def parse_duration(duration_str: str) -> float:
        """Parse Twitch duration string (e.g. '3h2m1s') to hours."""
        m = _DURATION_RE.match(duration_str)
        if not m:
            return 0.0
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        seconds = int(m.group(3) or 0)
        return hours + minutes / 60 + seconds / 3600
