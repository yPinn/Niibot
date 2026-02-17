"""Twitch API client service.

Token types:
- App Access Token: For public endpoints (users, streams, games). Auto-fetched and cached.
- User Access Token: For user-specific endpoints (channel:bot, redemptions).
  Requires OAuth flow, stored in DB, can be refreshed.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# Pre-compiled regex for duration parsing
_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")

HELIX_BASE = "https://api.twitch.tv/helix"
OAUTH_BASE = "https://id.twitch.tv/oauth2"


@dataclass
class TokenRefreshResult:
    """Result of a token refresh operation."""

    success: bool
    access_token: str | None = None
    refresh_token: str | None = None
    error: str | None = None


class TwitchAPIClient:
    """Client for interacting with Twitch API.

    Manages a shared httpx client for connection reuse and caches
    the app access token to avoid redundant token requests.
    """

    BROADCASTER_SCOPES = [
        "channel:bot",
        "channel:read:redemptions",
        "channel:read:subscriptions",
        "bits:read",
    ]

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

    async def close(self) -> None:
        """Close the shared HTTP client. Call on app shutdown."""
        await self._http.aclose()

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
                    logger.error(f"Failed to get app token: {response.status_code}")
                    return None

                data = response.json()
                self._app_token = data.get("access_token")
                # Twitch returns expires_in in seconds; refresh 5 min early
                expires_in = data.get("expires_in", 0)
                self._app_token_expires_at = now + max(expires_in - 300, 0)
                return self._app_token

            except Exception as e:
                logger.exception(f"Error getting app access token: {e}")
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
        try:
            return await self._http.get(
                f"{HELIX_BASE}/{path}",
                params=params,
                headers=self._app_headers(token),
            )
        except Exception as e:
            logger.exception(f"Helix GET /{path} error: {e}")
            return None

    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------

    def generate_oauth_url(self, state: str | None = None) -> str:
        """Generate Twitch OAuth authorization URL."""
        redirect_uri = f"{self.api_url}/api/auth/twitch/callback"
        scope_string = "+".join(s.replace(":", "%3A") for s in self.BROADCASTER_SCOPES)
        encoded_redirect_uri = quote(redirect_uri, safe="")

        url = (
            f"{OAUTH_BASE}/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_string}"
            f"&force_verify=true"
        )
        if state:
            url += f"&state={quote(state, safe='')}"
        return url

    async def exchange_code_for_token(
        self, code: str
    ) -> tuple[bool, str | None, dict[str, str] | None]:
        """Exchange OAuth code for access token.

        Returns:
            Tuple of (success, error_message, token_data)
            token_data contains: access_token, refresh_token, user_id
        """
        try:
            redirect_uri = f"{self.api_url}/api/auth/twitch/callback"

            token_response = await self._http.post(
                f"{OAUTH_BASE}/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )

            if token_response.status_code != 200:
                logger.error(f"Failed to exchange code: {token_response.status_code}")
                logger.error(f"Response: {token_response.text}")
                return False, "token_exchange_failed", None

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            if not access_token:
                logger.error("No access_token in response")
                return False, "no_access_token", None

            # Get user info with the new user token
            response = await self._helix_get("users", token=access_token)
            if not response or response.status_code != 200:
                return False, "user_fetch_failed", None

            users = response.json().get("data", [])
            if not users:
                return False, "user_fetch_failed", None

            user_id = users[0].get("id")
            logger.debug(f"Token exchanged for user: {user_id}")

            return (
                True,
                None,
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token or "",
                    "user_id": user_id,
                },
            )

        except httpx.TimeoutException:
            logger.error("Timeout while exchanging code for token")
            return False, "timeout", None
        except Exception as e:
            logger.exception(f"Unexpected error exchanging code: {e}")
            return False, "exchange_failed", None

    # ------------------------------------------------------------------
    # User token management
    # ------------------------------------------------------------------

    async def refresh_access_token(self, refresh_token: str) -> TokenRefreshResult:
        """Refresh a user's access token using their refresh token.

        The refresh token itself may also be rotated (Twitch returns a new one).
        Caller should update both tokens in the database.
        """
        try:
            response = await self._http.post(
                f"{OAUTH_BASE}/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("message", f"HTTP {response.status_code}")
                logger.error(f"Token refresh failed: {error_msg}")
                return TokenRefreshResult(success=False, error=error_msg)

            data = response.json()
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token")

            if not new_access_token:
                return TokenRefreshResult(
                    success=False, error="No access_token in refresh response"
                )

            logger.debug("Successfully refreshed user access token")
            return TokenRefreshResult(
                success=True,
                access_token=new_access_token,
                refresh_token=new_refresh_token or refresh_token,
            )

        except httpx.TimeoutException:
            logger.error("Timeout while refreshing token")
            return TokenRefreshResult(success=False, error="timeout")
        except Exception as e:
            logger.exception(f"Unexpected error refreshing token: {e}")
            return TokenRefreshResult(success=False, error=str(e))

    async def validate_token(self, access_token: str) -> bool:
        """Validate if an access token is still valid."""
        try:
            response = await self._http.get(
                f"{OAUTH_BASE}/validate",
                headers={"Authorization": f"OAuth {access_token}"},
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return False

    # ------------------------------------------------------------------
    # User data
    # ------------------------------------------------------------------

    async def get_user_by_login(self, login: str) -> dict[str, str] | None:
        """Look up a Twitch user by login name."""
        return await self._fetch_user(params={"login": login})

    async def get_user_info(self, user_id: str) -> dict[str, str] | None:
        """Get user information by Twitch user ID."""
        return await self._fetch_user(params={"id": user_id})

    async def _fetch_user(self, *, params: dict[str, str]) -> dict[str, str] | None:
        """Internal: fetch a single user from Twitch Helix API."""
        try:
            response = await self._helix_get("users", params)
            if not response or response.status_code != 200:
                logger.error(f"Failed to fetch user: params={params}")
                return None

            users = response.json().get("data", [])
            if not users:
                logger.warning(f"No user found for params: {params}")
                return None

            user = users[0]
            return {
                "id": user.get("id"),
                "name": user.get("login"),
                "display_name": user.get("display_name"),
                "avatar": user.get("profile_image_url"),
                "broadcaster_type": user.get("broadcaster_type", ""),
            }

        except Exception as e:
            logger.exception(f"Error fetching user info: {e}")
            return None

    async def get_users_by_ids(self, user_ids: list[str]) -> list[dict]:
        """Get multiple users by their IDs."""
        try:
            response = await self._helix_get("users", {"id": user_ids})
            if not response or response.status_code != 200:
                logger.error(f"Failed to fetch users: {len(user_ids)} ids")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception as e:
            logger.exception(f"Error getting users: {e}")
            return []

    # ------------------------------------------------------------------
    # Streams
    # ------------------------------------------------------------------

    async def get_streams(self, user_ids: list[str]) -> list[dict]:
        """Get stream information for multiple users."""
        try:
            response = await self._helix_get("streams", {"user_id": user_ids})
            if not response or response.status_code != 200:
                logger.error("Failed to fetch streams")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception as e:
            logger.exception(f"Error getting streams: {e}")
            return []

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------

    async def get_games_by_ids(self, game_ids: list[str]) -> list[dict]:
        """Get game information by game IDs."""
        if not game_ids:
            return []
        try:
            response = await self._helix_get("games", {"id": game_ids})
            if not response or response.status_code != 200:
                logger.error("Failed to fetch games by ids")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception as e:
            logger.exception(f"Error getting games: {e}")
            return []

    async def get_games_by_names(self, game_names: list[str]) -> list[dict]:
        """Get game information by game names."""
        if not game_names:
            return []
        try:
            response = await self._helix_get("games", {"name": game_names})
            if not response or response.status_code != 200:
                logger.error("Failed to fetch games by names")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception as e:
            logger.exception(f"Error getting games by names: {e}")
            return []

    # ------------------------------------------------------------------
    # Channel Points
    # ------------------------------------------------------------------

    async def get_custom_rewards(self, broadcaster_id: str, access_token: str) -> list[dict]:
        """Get custom channel point rewards (requires user token)."""
        try:
            response = await self._helix_get(
                "channel_points/custom_rewards",
                {"broadcaster_id": broadcaster_id},
                token=access_token,
            )
            if not response or response.status_code != 200:
                logger.error(f"Failed to fetch custom rewards: broadcaster={broadcaster_id}")
                return []

            return [
                {"id": r["id"], "title": r["title"], "cost": r["cost"]}
                for r in response.json().get("data", [])
            ]

        except Exception as e:
            logger.exception(f"Error getting custom rewards: {e}")
            return []

    # ------------------------------------------------------------------
    # Videos / VODs
    # ------------------------------------------------------------------

    async def get_videos(
        self,
        user_id: str,
        video_type: str = "archive",
        first: int = 20,
    ) -> list[dict]:
        """Get videos (VODs) for a user."""
        try:
            response = await self._helix_get(
                "videos",
                {"user_id": user_id, "type": video_type, "first": min(first, 100)},
            )
            if not response or response.status_code != 200:
                logger.error(f"Failed to fetch videos: user={user_id}")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception as e:
            logger.exception(f"Error getting videos: {e}")
            return []

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
