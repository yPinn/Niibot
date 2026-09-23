"""Moderator, VIP, subscriber, and follower list queries for TwitchAPIClient."""

import logging

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

    async def fetch_all_followers(
        self, broadcaster_id: str, token: str, moderator_id: str
    ) -> list[dict]:
        """Return all followers for a channel.

        `token` is the bot's token and `moderator_id` is the bot's user id — the
        bot reads followers as a moderator (moderator:read:followers lives on the
        bot, not the broadcaster). Requires the bot to be a mod of the channel.

        Each dict contains user_id, user_login, user_name, followed_at.
        Returns empty list on error, missing scope, or bot-not-mod (403).
        """
        try:
            results = await self._fetch_paginated(
                "channels/followers",
                {"broadcaster_id": broadcaster_id, "moderator_id": moderator_id},
                token=token,
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

    async def fetch_all_banned(
        self, broadcaster_id: str, token: str, moderator_id: str
    ) -> list[dict]:
        """Return the channel's currently banned + timed-out users.

        Read with the bot's token as a moderator (`moderator:manage:banned_users`
        lives on the bot). Requires the bot to be a mod of the channel; returns
        an empty list on error, missing scope, or 403.

        Each dict has user_id, user_login, user_name, expires_at (ISO string or
        None for a permanent ban), reason.
        """
        try:
            results = await self._fetch_paginated(
                "moderation/banned",
                {"broadcaster_id": broadcaster_id, "moderator_id": moderator_id},
                token=token,
            )
            return [
                {
                    "user_id": r["user_id"],
                    "user_login": r.get("user_login", ""),
                    "user_name": r.get("user_name"),
                    "expires_at": r.get("expires_at") or None,
                    "reason": r.get("reason") or None,
                }
                for r in results
                if r.get("user_id")
            ]
        except Exception:
            LOGGER.exception("Error fetching banned users for %s", broadcaster_id)
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
        """Return mod relation or a credential, scope, or provider failure class.

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
                return "provider_unavailable"
            if response.status_code == 401:
                return "token_error"
            if response.status_code == 403:
                return "scope_error"
            if response.status_code != 200:
                return "provider_unavailable"
            return "mod" if len(response.json().get("data", [])) > 0 else "no_mod"
        except Exception:
            LOGGER.exception(
                "Error checking detailed mod status for broadcaster %s", broadcaster_id
            )
            return "provider_unavailable"

    async def add_moderator(
        self, broadcaster_id: str, moderator_user_id: str, access_token: str
    ) -> httpx.Response:
        """Grant moderator status. Returns the raw Helix response for caller inspection."""
        return await self._http.post(
            f"{HELIX_BASE}/moderation/moderators",
            params={"broadcaster_id": broadcaster_id, "user_id": moderator_user_id},
            headers=self._app_headers(access_token),
        )
