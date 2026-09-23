"""OAuth authorization-code flow and user-token management for TwitchAPIClient."""

import logging
from dataclasses import dataclass
from typing import Literal
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
    error_code: Literal["refresh_failed", "provider_unavailable"] | None = None


@dataclass(frozen=True)
class TokenValidationResult:
    """Structured token validation result without collapsing outages into revocation."""

    status: Literal["valid", "invalid", "unavailable"]
    client_id: str | None = None
    login: str | None = None
    user_id: str | None = None
    scopes: frozenset[str] = frozenset()
    expires_in: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class TokenRevocationResult:
    """Idempotent result of asking Twitch to revoke a user access token."""

    status: Literal["revoked", "already_invalid", "unavailable"]
    error_code: str | None = None


class _OAuthMixin(_TwitchAPIBase):
    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------

    def generate_oauth_url(
        self,
        state: str | None = None,
        *,
        scopes: list[str] | None = None,
        redirect_path: str = "/api/auth/twitch/callback",
    ) -> str:
        """Generate Twitch OAuth authorization URL."""
        if not redirect_path.startswith("/api/auth/twitch/") or "?" in redirect_path:
            raise ValueError("redirect_path must be an internal Twitch auth callback")
        redirect_uri = f"{self.api_url}{redirect_path}"
        requested_scopes = self.BROADCASTER_SCOPES if scopes is None else scopes
        scope_string = "+".join(s.replace(":", "%3A") for s in requested_scopes)
        encoded_redirect_uri = quote(redirect_uri, safe="")

        url = (
            f"{OAUTH_BASE}/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&response_type=code"
            f"&force_verify=true"
        )
        if scope_string:
            url += f"&scope={scope_string}"
        if state:
            url += f"&state={quote(state, safe='')}"
        return url

    async def exchange_code_for_token(
        self,
        code: str,
        *,
        redirect_path: str = "/api/auth/twitch/callback",
    ) -> tuple[bool, str | None, dict[str, str] | None]:
        """Exchange OAuth code for access token.

        Returns:
            Tuple of (success, error_message, token_data)
            token_data contains: access_token, refresh_token, user_id
        """
        try:
            if not redirect_path.startswith("/api/auth/twitch/") or "?" in redirect_path:
                raise ValueError("redirect_path must be an internal Twitch auth callback")
            redirect_uri = f"{self.api_url}{redirect_path}"

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
                error_code: Literal["refresh_failed", "provider_unavailable"] = (
                    "refresh_failed"
                    if response.status_code in {400, 401}
                    else "provider_unavailable"
                )
                LOGGER.warning("Twitch token refresh failed: HTTP %s", response.status_code)
                return TokenRefreshResult(success=False, error=error_msg, error_code=error_code)

            data = response.json()
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token")

            if not new_access_token:
                return TokenRefreshResult(
                    success=False,
                    error="No access_token in refresh response",
                    error_code="provider_unavailable",
                )

            LOGGER.debug("Successfully refreshed user access token")
            return TokenRefreshResult(
                success=True,
                access_token=new_access_token,
                refresh_token=new_refresh_token or refresh_token,
            )

        except httpx.TimeoutException:
            LOGGER.error("Timeout refreshing user token")
            return TokenRefreshResult(
                success=False, error="timeout", error_code="provider_unavailable"
            )
        except Exception as e:
            LOGGER.exception("Unexpected error refreshing user token")
            return TokenRefreshResult(
                success=False, error=str(e), error_code="provider_unavailable"
            )

    async def validate_token_details(self, access_token: str) -> TokenValidationResult:
        """Validate a token while preserving invalid-vs-provider-outage semantics."""
        try:
            response = await self._http.get(
                f"{OAUTH_BASE}/validate",
                headers={"Authorization": f"OAuth {access_token}"},
            )
            if response.status_code == 401:
                return TokenValidationResult(status="invalid", error_code="invalid_token")
            if response.status_code != 200:
                LOGGER.warning("Twitch token validation unavailable: HTTP %s", response.status_code)
                return TokenValidationResult(
                    status="unavailable", error_code="provider_unavailable"
                )

            data = response.json()
            client_id = data.get("client_id")
            user_id = data.get("user_id")
            login = data.get("login")
            scopes = data.get("scopes")
            expires_in = data.get("expires_in")
            if (
                not isinstance(client_id, str)
                or not isinstance(user_id, str)
                or not isinstance(login, str)
                or not isinstance(scopes, list)
                or not all(isinstance(scope, str) for scope in scopes)
                or not isinstance(expires_in, int)
            ):
                LOGGER.warning("Twitch token validation returned a malformed success response")
                return TokenValidationResult(
                    status="unavailable", error_code="provider_unavailable"
                )

            return TokenValidationResult(
                status="valid",
                client_id=client_id,
                login=login,
                user_id=user_id,
                scopes=frozenset(scopes),
                expires_in=expires_in,
            )
        except (httpx.HTTPError, ValueError, TypeError):
            LOGGER.warning("Twitch token validation request failed", exc_info=True)
            return TokenValidationResult(status="unavailable", error_code="provider_unavailable")

    async def validate_token(self, access_token: str) -> bool:
        """Compatibility wrapper for callers that only need valid or not-valid."""
        return (await self.validate_token_details(access_token)).status == "valid"

    async def revoke_access_token(self, access_token: str) -> TokenRevocationResult:
        """Revoke a user token without exposing credential or provider response details."""
        try:
            response = await self._http.post(
                f"{OAUTH_BASE}/revoke",
                data={"client_id": self.client_id, "token": access_token},
            )
            if response.status_code == 200:
                return TokenRevocationResult(status="revoked")
            if response.status_code == 400:
                return TokenRevocationResult(status="already_invalid")
            LOGGER.warning("Twitch token revocation unavailable: HTTP %s", response.status_code)
            return TokenRevocationResult(status="unavailable", error_code="provider_unavailable")
        except httpx.HTTPError:
            LOGGER.warning("Twitch token revocation request failed", exc_info=True)
            return TokenRevocationResult(status="unavailable", error_code="provider_unavailable")
