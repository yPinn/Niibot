"""Twitch API client service.

Token types:
- App Access Token: For public endpoints (users, streams, games). Auto-fetched.
- User Access Token: For user-specific endpoints (channel:bot, redemptions).
  Requires OAuth flow, stored in DB, can be refreshed.
"""

import logging
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TokenRefreshResult:
    """Result of a token refresh operation."""

    success: bool
    access_token: str | None = None
    refresh_token: str | None = None
    error: str | None = None


class TwitchAPIClient:
    """Client for interacting with Twitch API"""

    # Broadcaster OAuth scopes - minimal scopes for channel authorization
    # Bot account handles all operations, broadcaster just grants access
    BROADCASTER_SCOPES = [
        "channel:bot",  # Allow bot to join channel
        "channel:read:redemptions",  # Channel points EventSub
        "channel:read:subscriptions",  # Subscription EventSub
        "bits:read",  # Bits EventSub
    ]

    def __init__(self, client_id: str, client_secret: str, api_url: str):
        if not client_id or not client_secret:
            raise ValueError("Twitch client_id and client_secret are required")

        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = api_url
        self.timeout = 10.0

    def generate_oauth_url(self, state: str | None = None) -> str:
        """Generate Twitch OAuth authorization URL"""
        redirect_uri = f"{self.api_url}/api/auth/twitch/callback"
        scope_string = "+".join(s.replace(":", "%3A") for s in self.BROADCASTER_SCOPES)
        encoded_redirect_uri = quote(redirect_uri, safe="")

        url = (
            f"https://id.twitch.tv/oauth2/authorize"
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
        """
        Exchange OAuth code for access token

        Returns:
            Tuple of (success, error_message, token_data)
            token_data contains: access_token, refresh_token, user_id
        """
        try:
            redirect_uri = f"{self.api_url}/api/auth/twitch/callback"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Exchange code for token
                token_response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
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

                # Get user info
                user_id = await self._get_user_id(access_token)
                if not user_id:
                    return False, "user_fetch_failed", None

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

    async def _get_user_id(self, access_token: str) -> str | None:
        """Get user ID from access token"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/users",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to get user info: {response.status_code}")
                    return None

                data = response.json()
                users = data.get("data", [])

                if not users:
                    logger.error("No user data in response")
                    return None

                return cast(str | None, users[0].get("id"))

        except Exception as e:
            logger.exception(f"Error getting user ID: {e}")
            return None

    async def get_user_by_login(self, login: str) -> dict[str, str] | None:
        """Look up a Twitch user by login name (e.g. 'llazypilot')."""
        return await self._fetch_user(params={"login": login})

    async def get_user_info(self, user_id: str) -> dict[str, str] | None:
        """Get user information by Twitch user ID."""
        return await self._fetch_user(params={"id": user_id})

    async def _fetch_user(self, *, params: dict[str, str]) -> dict[str, str] | None:
        """Internal: fetch a single user from Twitch Helix API."""
        try:
            # Get app access token
            app_token = await self._get_app_access_token()
            if not app_token:
                return None

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/users",
                    params=params,
                    headers={
                        "Client-ID": self.client_id,
                        "Authorization": f"Bearer {app_token}",
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch user: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return None

                data = response.json()
                users = data.get("data", [])

                if not users:
                    logger.warning(f"No user found for params: {params}")
                    return None

                user = users[0]
                return {
                    "id": user.get("id"),
                    "name": user.get("login"),
                    "display_name": user.get("display_name"),
                    "avatar": user.get("profile_image_url"),
                }

        except Exception as e:
            logger.exception(f"Error fetching user info: {e}")
            return None

    async def _get_app_access_token(self) -> str | None:
        """Get app access token for API calls"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials",
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to get app token: {response.status_code}")
                    return None

                data = response.json()
                return cast(str | None, data.get("access_token"))

        except Exception as e:
            logger.exception(f"Error getting app access token: {e}")
            return None

    async def get_users_by_ids(
        self, user_ids: list[str], access_token: str | None = None
    ) -> list[dict]:
        """Get multiple users by their IDs (uses app token)"""
        try:
            # Use app token instead of user token (more reliable)
            app_token = await self._get_app_access_token()
            if not app_token:
                logger.error("Failed to get app token for get_users_by_ids")
                return []

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/users",
                    params={"id": user_ids},
                    headers={
                        "Authorization": f"Bearer {app_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch users: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return []

                data = response.json()
                return cast(list[dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting users: {e}")
            return []

    async def get_streams(self, user_ids: list[str], access_token: str | None = None) -> list[dict]:
        """Get stream information for multiple users (uses app token)"""
        try:
            # Use app token instead of user token (more reliable)
            app_token = await self._get_app_access_token()
            if not app_token:
                logger.error("Failed to get app token for get_streams")
                return []

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/streams",
                    params={"user_id": user_ids},
                    headers={
                        "Authorization": f"Bearer {app_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch streams: {response.status_code}")
                    return []

                data = response.json()
                return cast(list[dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting streams: {e}")
            return []

    async def get_games_by_ids(self, game_ids: list[str]) -> list[dict]:
        """
        Get game information by game IDs

        Returns list of game objects with:
        - id: Game ID
        - name: Game name
        - box_art_url: Template URL (replace {width} and {height})
        """
        try:
            if not game_ids:
                return []

            # Get app access token
            app_token = await self._get_app_access_token()
            if not app_token:
                return []

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/games",
                    params={"id": game_ids},
                    headers={
                        "Authorization": f"Bearer {app_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch games: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return []

                data = response.json()
                return cast(list[dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting games: {e}")
            return []

    async def get_games_by_names(self, game_names: list[str]) -> list[dict]:
        """
        Get game information by game names

        Returns list of game objects with:
        - id: Game ID
        - name: Game name
        - box_art_url: Template URL (replace {width} and {height})
        """
        try:
            if not game_names:
                return []

            # Get app access token
            app_token = await self._get_app_access_token()
            if not app_token:
                return []

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/games",
                    params={"name": game_names},
                    headers={
                        "Authorization": f"Bearer {app_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch games by names: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return []

                data = response.json()
                return cast(list[dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting games by names: {e}")
            return []

    # ==================== Channel Points ====================

    async def get_custom_rewards(self, broadcaster_id: str, access_token: str) -> list[dict]:
        """Get custom channel point rewards for a broadcaster (requires user token)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/channel_points/custom_rewards",
                    params={"broadcaster_id": broadcaster_id},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch custom rewards: {response.status_code}")
                    return []

                data = response.json()
                return [
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "cost": r["cost"],
                    }
                    for r in data.get("data", [])
                ]

        except Exception as e:
            logger.exception(f"Error getting custom rewards: {e}")
            return []

    # ==================== User Token Management ====================

    async def refresh_access_token(self, refresh_token: str) -> TokenRefreshResult:
        """
        Refresh a user's access token using their refresh token.

        The refresh token itself may also be rotated (Twitch returns a new one).
        Caller should update both tokens in the database.

        Returns:
            TokenRefreshResult with new tokens on success, error on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
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
        """
        Validate if an access token is still valid.

        Returns True if valid, False if expired or invalid.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {access_token}"},
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return False

    # ==================== Video / VOD API ====================

    async def get_videos(
        self,
        user_id: str,
        video_type: str = "archive",
        first: int = 20,
    ) -> list[dict]:
        """
        Get videos (VODs) for a user from Twitch API.

        Args:
            user_id: The Twitch user ID to fetch videos for
            video_type: Type of video - "archive" (past broadcasts), "highlight", "upload"
            first: Number of videos to return (max 100)

        Returns:
            List of video objects with:
            - id: Video ID
            - stream_id: Original stream ID (if archive)
            - user_id: Broadcaster user ID
            - user_name: Broadcaster display name
            - title: Video title
            - created_at: When the video was created (ISO 8601)
            - published_at: When the video was published
            - duration: Duration string (e.g., "3h2m1s")
            - view_count: Number of views
            - type: Video type (archive, highlight, upload)
        """
        try:
            app_token = await self._get_app_access_token()
            if not app_token:
                logger.error("Failed to get app token for get_videos")
                return []

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/videos",
                    params={
                        "user_id": user_id,
                        "type": video_type,
                        "first": min(first, 100),
                    },
                    headers={
                        "Authorization": f"Bearer {app_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch videos: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return []

                data = response.json()
                return cast(list[dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting videos: {e}")
            return []

    def parse_duration(self, duration_str: str) -> float:
        """
        Parse Twitch duration string to hours.

        Args:
            duration_str: Duration like "3h2m1s", "45m30s", "1h30s"

        Returns:
            Duration in hours as float
        """
        import re

        hours = 0
        minutes = 0
        seconds = 0

        h_match = re.search(r"(\d+)h", duration_str)
        m_match = re.search(r"(\d+)m", duration_str)
        s_match = re.search(r"(\d+)s", duration_str)

        if h_match:
            hours = int(h_match.group(1))
        if m_match:
            minutes = int(m_match.group(1))
        if s_match:
            seconds = int(s_match.group(1))

        return hours + minutes / 60 + seconds / 3600
