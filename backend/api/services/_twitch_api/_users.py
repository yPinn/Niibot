"""User, channel, stream, and game lookups for TwitchAPIClient."""

import logging
from typing import cast

from services._twitch_api._base import _TwitchAPIBase

LOGGER: logging.Logger = logging.getLogger(__name__)


class _UsersMixin(_TwitchAPIBase):
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
                LOGGER.error(f"Failed to fetch user: params={params}")
                return None

            users = response.json().get("data", [])
            if not users:
                LOGGER.warning(f"No user found for params: {params}")
                return None

            user = users[0]
            return {
                "id": user.get("id"),
                "name": user.get("login"),
                "display_name": user.get("display_name"),
                "avatar": user.get("profile_image_url"),
                "offline_image_url": user.get("offline_image_url") or None,
                "broadcaster_type": user.get("broadcaster_type", ""),
                "account_created_at": user.get("created_at"),
            }

        except Exception:
            LOGGER.exception("Error fetching user info: params=%s", params)
            return None

    async def get_users_by_ids(self, user_ids: list[str]) -> list[dict]:
        """Get multiple users by their IDs."""
        try:
            response = await self._helix_get("users", {"id": user_ids})
            if not response or response.status_code != 200:
                LOGGER.error(f"Failed to fetch users: {len(user_ids)} ids")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception:
            LOGGER.exception("Error getting users by ids (count=%d)", len(user_ids))
            return []

    async def get_channels_info(self, broadcaster_ids: list[str]) -> list[dict]:
        """Get channel info (language, tags) for multiple broadcasters via /helix/channels."""
        if not broadcaster_ids:
            return []
        try:
            response = await self._helix_get("channels", {"broadcaster_id": broadcaster_ids})
            if not response or response.status_code != 200:
                LOGGER.error("Failed to fetch channels info for %d ids", len(broadcaster_ids))
                return []
            return cast(list[dict], response.json().get("data", []))
        except Exception:
            LOGGER.exception("Error getting channels info (count=%d)", len(broadcaster_ids))
            return []

    # ------------------------------------------------------------------
    # Streams
    # ------------------------------------------------------------------

    async def get_streams(self, user_ids: list[str]) -> list[dict]:
        """Get stream information for multiple users."""
        try:
            response = await self._helix_get("streams", {"user_id": user_ids})
            if not response or response.status_code != 200:
                LOGGER.error("Failed to fetch streams")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception:
            LOGGER.exception("Error getting streams")
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
                LOGGER.error("Failed to fetch games by ids")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception:
            LOGGER.exception("Error getting games by ids")
            return []

    async def get_games_by_names(self, game_names: list[str]) -> list[dict]:
        """Get game information by game names."""
        if not game_names:
            return []
        try:
            response = await self._helix_get("games", {"name": game_names})
            if not response or response.status_code != 200:
                LOGGER.error("Failed to fetch games by names")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception:
            LOGGER.exception("Error getting games by names")
            return []
