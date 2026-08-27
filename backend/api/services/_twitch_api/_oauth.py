"""OAuth authorization-code flow and user-token management for TwitchAPIClient."""

import logging
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from services._twitch_api._base import OAUTH_BASE, _TwitchAPIBase

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass
class TokenRefreshResult:
    """Result of a token refresh operation."""

    success: bool
    access_token: str | None = None
    refresh_token: str | None = None
    error: str | None = None


class _OAuthMixin(_TwitchAPIBase):
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
                try:
                    error_msg = token_response.json().get("message", "unknown")
                except Exception:
                    error_msg = "unparseable"
                LOGGER.error(
                    f"Failed to exchange code: status={token_response.status_code} error={error_msg}"
                )
                return False, "token_exchange_failed", None

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            scope_list: list[str] = token_data.get("scope") or []

            if not access_token:
                LOGGER.error("No access_token in response")
                return False, "no_access_token", None

            # Get user info with the new user token
            response = await self._helix_get("users", token=access_token)
            if not response or response.status_code != 200:
                return False, "user_fetch_failed", None

            users = response.json().get("data", [])
            if not users:
                return False, "user_fetch_failed", None

            user_id = users[0].get("id")
            LOGGER.debug(f"Token exchanged for user: {user_id}")

            return (
                True,
                None,
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token or "",
                    "user_id": user_id,
                    "scopes": " ".join(scope_list) if scope_list else None,
                },
            )

        except httpx.TimeoutException:
            LOGGER.error("Timeout exchanging OAuth code for token")
            return False, "timeout", None
        except Exception:
            LOGGER.exception("Unexpected error exchanging OAuth code")
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
                LOGGER.error(f"Token refresh failed: {error_msg}")
                return TokenRefreshResult(success=False, error=error_msg)

            data = response.json()
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token")

            if not new_access_token:
                return TokenRefreshResult(
                    success=False, error="No access_token in refresh response"
                )

            LOGGER.debug("Successfully refreshed user access token")
            return TokenRefreshResult(
                success=True,
                access_token=new_access_token,
                refresh_token=new_refresh_token or refresh_token,
            )

        except httpx.TimeoutException:
            LOGGER.error("Timeout refreshing user token")
            return TokenRefreshResult(success=False, error="timeout")
        except Exception as e:
            LOGGER.exception("Unexpected error refreshing user token")
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
            LOGGER.warning(f"Token validation failed: {e}")
            return False
