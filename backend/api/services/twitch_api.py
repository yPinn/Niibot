"""Twitch API client service"""

import logging
from typing import Dict, List, Optional, Tuple, cast
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class TwitchAPIClient:
    """Client for interacting with Twitch API"""

    # Broadcaster OAuth scopes
    BROADCASTER_SCOPES = [
        "user:read:email",
        "channel:read:subscriptions",
        "bits:read",
        "channel:read:redemptions",
        "moderator:read:followers",
    ]

    def __init__(self, client_id: str, client_secret: str, api_url: str):
        if not client_id or not client_secret:
            raise ValueError("Twitch client_id and client_secret are required")

        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = api_url
        self.timeout = 10.0

    def generate_oauth_url(self) -> str:
        """Generate Twitch OAuth authorization URL"""
        redirect_uri = f"{self.api_url}/api/auth/twitch/callback"
        scope_string = "+".join(s.replace(":", "%3A")
                                for s in self.BROADCASTER_SCOPES)
        encoded_redirect_uri = quote(redirect_uri, safe="")

        return (
            f"https://id.twitch.tv/oauth2/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_string}"
            f"&force_verify=true"
        )

    async def exchange_code_for_token(
        self, code: str
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, str]]]:
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
                    logger.error(
                        f"Failed to exchange code: {token_response.status_code}")
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

                return True, None, {
                    "access_token": access_token,
                    "refresh_token": refresh_token or "",
                    "user_id": user_id,
                }

        except httpx.TimeoutException:
            logger.error("Timeout while exchanging code for token")
            return False, "timeout", None
        except Exception as e:
            logger.exception(f"Unexpected error exchanging code: {e}")
            return False, "exchange_failed", None

    async def _get_user_id(self, access_token: str) -> Optional[str]:
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
                    logger.error(
                        f"Failed to get user info: {response.status_code}")
                    return None

                data = response.json()
                users = data.get("data", [])

                if not users:
                    logger.error("No user data in response")
                    return None

                return cast(Optional[str], users[0].get("id"))

        except Exception as e:
            logger.exception(f"Error getting user ID: {e}")
            return None

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, str]]:
        """Get user information from Twitch API using app access token"""
        try:
            # Get app access token
            app_token = await self._get_app_access_token()
            if not app_token:
                return None

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"https://api.twitch.tv/helix/users?id={user_id}",
                    headers={
                        "Client-ID": self.client_id,
                        "Authorization": f"Bearer {app_token}",
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch user: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return None

                data = response.json()
                users = data.get("data", [])

                if not users:
                    logger.warning(f"No user found for user_id: {user_id}")
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

    async def _get_app_access_token(self) -> Optional[str]:
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
                    logger.error(
                        f"Failed to get app token: {response.status_code}")
                    return None

                data = response.json()
                return cast(Optional[str], data.get("access_token"))

        except Exception as e:
            logger.exception(f"Error getting app access token: {e}")
            return None

    async def get_users_by_ids(self, user_ids: List[str], access_token: str) -> List[Dict]:
        """Get multiple users by their IDs"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/users",
                    params={"id": user_ids},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch users: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return []

                data = response.json()
                return cast(List[Dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting users: {e}")
            return []

    async def get_streams(self, user_ids: List[str], access_token: str) -> List[Dict]:
        """Get stream information for multiple users"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.twitch.tv/helix/streams",
                    params={"user_id": user_ids},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": self.client_id,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch streams: {response.status_code}")
                    return []

                data = response.json()
                return cast(List[Dict], data.get("data", []))

        except Exception as e:
            logger.exception(f"Error getting streams: {e}")
            return []
