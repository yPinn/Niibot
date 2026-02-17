"""Discord API client service"""

import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class DiscordAPIClient:
    """Client for interacting with Discord OAuth2 API"""

    # Discord OAuth scopes
    OAUTH_SCOPES = [
        "identify",
        "email",
    ]

    DISCORD_API_URL = "https://discord.com/api/v10"
    DISCORD_OAUTH_URL = "https://discord.com/api/oauth2"

    def __init__(self, client_id: str, client_secret: str, api_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = api_url

        # Shared HTTP client — reuses TCP connections across requests
        self._http = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        """Close the shared HTTP client. Call on app shutdown."""
        await self._http.aclose()

    @property
    def is_configured(self) -> bool:
        """Check if Discord OAuth is configured"""
        return bool(self.client_id and self.client_secret)

    def generate_oauth_url(self, state: str | None = None) -> str:
        """Generate Discord OAuth authorization URL"""
        redirect_uri = f"{self.api_url}/api/auth/discord/callback"
        scope_string = "%20".join(self.OAUTH_SCOPES)
        encoded_redirect_uri = quote(redirect_uri, safe="")

        url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_string}"
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
            redirect_uri = f"{self.api_url}/api/auth/discord/callback"

            token_response = await self._http.post(
                f"{self.DISCORD_OAUTH_URL}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                auth=(self.client_id, self.client_secret),
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
            user_info = await self._get_user_info(access_token)
            if not user_info:
                return False, "user_fetch_failed", None

            user_id = user_info.get("id")
            logger.debug(f"Token exchanged for Discord user: {user_id}")

            return (
                True,
                None,
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token or "",
                    "user_id": user_id,
                    "username": user_info.get("username", ""),
                    "global_name": user_info.get("global_name"),  # Display name
                    "discriminator": user_info.get("discriminator", "0"),
                    "avatar": user_info.get("avatar"),
                    "email": user_info.get("email"),
                },
            )

        except httpx.TimeoutException:
            logger.error("Timeout while exchanging code for token")
            return False, "timeout", None
        except Exception as e:
            logger.exception(f"Unexpected error exchanging code: {e}")
            return False, "exchange_failed", None

    async def _get_user_info(self, access_token: str) -> dict[str, str] | None:
        """Get user info from access token"""
        try:
            response = await self._http.get(
                f"{self.DISCORD_API_URL}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(f"Failed to get user info: {response.status_code}")
                return None

            data: dict[str, str] = response.json()
            return data

        except Exception as e:
            logger.exception(f"Error getting user info: {e}")
            return None

    async def get_user_info(self, user_id: str) -> dict[str, str] | None:
        """Get user information (requires bot token, not implemented for OAuth)"""
        # Discord OAuth doesn't provide a way to fetch user info by ID
        # This would require a bot token
        logger.warning("get_user_info by ID is not supported for Discord OAuth")
        return None

    def get_avatar_url(self, user_id: str, avatar_hash: str | None) -> str:
        """Generate Discord avatar URL"""
        if avatar_hash:
            ext = "gif" if avatar_hash.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}"
        # Default avatar
        default_avatar_index = int(user_id) % 5
        return f"https://cdn.discordapp.com/embed/avatars/{default_avatar_index}.png"
