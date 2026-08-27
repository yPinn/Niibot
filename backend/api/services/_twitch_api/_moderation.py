"""Moderation, VIP, subscription, ban, and bits queries for TwitchAPIClient."""

import logging
from typing import cast

import httpx

from services._twitch_api._base import HELIX_BASE, _TwitchAPIBase

LOGGER: logging.Logger = logging.getLogger(__name__)


class _ModerationMixin(_TwitchAPIBase):
    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------

    async def fetch_all_moderators(self, broadcaster_id: str, token: str) -> list[dict]:
        """Return all moderators for a channel (requires moderation:read scope)."""
        try:
            return await self._fetch_paginated(
                "moderation/moderators", {"broadcaster_id": broadcaster_id}, token=token
            )
        except Exception:
            LOGGER.exception("Error fetching all moderators for %s", broadcaster_id)
            return []

    async def fetch_all_vips(self, broadcaster_id: str, token: str) -> list[dict]:
        """Return all VIPs for a channel (requires channel:read:vips scope)."""
        try:
            return await self._fetch_paginated(
                "channels/vips", {"broadcaster_id": broadcaster_id}, token=token
            )
        except Exception:
            LOGGER.exception("Error fetching all VIPs for %s", broadcaster_id)
            return []

    async def fetch_all_subscribers(self, broadcaster_id: str, token: str) -> list[dict]:
        """Return all subscribers for a channel (requires channel:read:subscriptions scope)."""
        try:
            return await self._fetch_paginated(
                "subscriptions", {"broadcaster_id": broadcaster_id}, token=token
            )
        except Exception:
            LOGGER.exception("Error fetching all subscribers for %s", broadcaster_id)
            return []

    async def fetch_all_followers(self, broadcaster_id: str, token: str) -> list[dict]:
        """Return all followers for a channel (requires moderator:read:followers scope).

        Each dict contains user_id, user_login, user_name, followed_at.
        Returns empty list on error or missing scope.
        """
        try:
            results = await self._fetch_paginated(
                "channels/followers", {"broadcaster_id": broadcaster_id}, token=token
            )
            return [
                {
                    "user_id": r["user_id"],
                    "user_login": r.get("user_login", ""),
                    "user_name": r.get("user_name"),
                    "followed_at": r["followed_at"],
                }
                for r in results
                if r.get("user_id") and r.get("followed_at")
            ]
        except Exception:
            LOGGER.exception("Error fetching all followers for %s", broadcaster_id)
            return []

    async def check_bot_is_moderator(
        self, broadcaster_id: str, bot_id: str, access_token: str
    ) -> bool:
        """Return True if bot_id is currently a moderator in broadcaster_id's channel."""
        try:
            response = await self._helix_get(
                "moderation/moderators",
                {"broadcaster_id": broadcaster_id, "user_id": bot_id},
                token=access_token,
            )
            if not response or response.status_code != 200:
                return False
            return len(response.json().get("data", [])) > 0
        except Exception:
            LOGGER.exception("Error checking moderator status for broadcaster %s", broadcaster_id)
            return False

    async def get_bot_mod_status(self, broadcaster_id: str, bot_id: str, access_token: str) -> str:
        """Detailed mod check: returns 'mod', 'no_mod', 'scope_error', or 'token_error'.

        scope_error means the token is valid but lacks moderation:read — the channel
        owner must re-authorize to grant the scope added after their initial auth.
        """
        try:
            response = await self._helix_get(
                "moderation/moderators",
                {"broadcaster_id": broadcaster_id, "user_id": bot_id},
                token=access_token,
            )
            if response is None:
                return "token_error"
            if response.status_code == 401:
                return "scope_error"
            if response.status_code != 200:
                return "token_error"
            return "mod" if len(response.json().get("data", [])) > 0 else "no_mod"
        except Exception:
            LOGGER.exception(
                "Error checking detailed mod status for broadcaster %s", broadcaster_id
            )
            return "token_error"

    async def get_mod_status(self, broadcaster_id: str, user_id: str, token: str) -> bool:
        """Return True if user_id is currently a moderator in broadcaster_id's channel."""
        try:
            response = await self._helix_get(
                "moderation/moderators",
                {"broadcaster_id": broadcaster_id, "user_id": user_id},
                token=token,
            )
            if not response or response.status_code != 200:
                return False
            return len(response.json().get("data", [])) > 0
        except Exception as e:
            LOGGER.warning(f"Error checking mod status for viewer {user_id}: {e}")
            return False

    async def get_vip_status(self, broadcaster_id: str, user_id: str, token: str) -> bool:
        """Return True if user_id is a VIP in broadcaster_id's channel."""
        try:
            response = await self._helix_get(
                "channels/vips",
                {"broadcaster_id": broadcaster_id, "user_id": user_id},
                token=token,
            )
            if not response or response.status_code != 200:
                return False
            return len(response.json().get("data", [])) > 0
        except Exception as e:
            LOGGER.warning(f"Error checking VIP status for viewer {user_id}: {e}")
            return False

    async def get_ban_status(self, broadcaster_id: str, user_id: str, token: str) -> dict | None:
        """Return ban info dict if user_id is banned, else None.

        Requires moderation:read scope on broadcaster token.
        Returns {"expires_at": str|None, "reason": str|None} when banned.
        expires_at is None for permanent bans.
        """
        try:
            response = await self._helix_get(
                "moderation/banned",
                {"broadcaster_id": broadcaster_id, "user_id": user_id},
                token=token,
            )
            if not response or response.status_code != 200:
                return None
            data = response.json().get("data", [])
            if not data:
                return None
            ban = data[0]
            return {
                "expires_at": ban.get("expires_at") or None,
                "reason": ban.get("reason") or None,
            }
        except Exception as e:
            LOGGER.warning(f"Error checking ban status for viewer {user_id}: {e}")
            return None

    async def get_bits_rank(self, user_id: str, token: str) -> int | None:
        """Return broadcaster-channel bits leaderboard rank for user_id, or None if unranked.

        Uses the broadcaster token (bits:read scope). The broadcaster is implicit in the token.
        """
        try:
            response = await self._helix_get(
                "bits/leaderboard",
                {"user_id": user_id, "period": "all"},
                token=token,
            )
            if not response or response.status_code != 200:
                return None
            data = response.json().get("data", [])
            if not data:
                return None
            return cast(int | None, data[0].get("rank"))
        except Exception as e:
            LOGGER.warning(f"Error fetching bits rank for viewer {user_id}: {e}")
            return None

    async def add_moderator(
        self, broadcaster_id: str, moderator_user_id: str, access_token: str
    ) -> httpx.Response:
        """Grant moderator status. Returns the raw Helix response for caller inspection."""
        return await self._http.post(
            f"{HELIX_BASE}/moderation/moderators",
            params={"broadcaster_id": broadcaster_id, "user_id": moderator_user_id},
            headers=self._app_headers(access_token),
        )
