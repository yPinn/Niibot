"""Channel points, VODs, subscriptions, badges, and emotes for TwitchAPIClient."""

import logging
from typing import cast

from services._twitch_api._base import HELIX_BASE, _TwitchAPIBase

LOGGER: logging.Logger = logging.getLogger(__name__)


class _ChannelMixin(_TwitchAPIBase):
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
                LOGGER.error(f"Failed to fetch custom rewards: broadcaster={broadcaster_id}")
                return []

            rewards: list[dict] = []
            for reward in response.json().get("data", []):
                stream_limit = reward.get("max_per_stream_setting") or {}
                user_limit = reward.get("max_per_user_per_stream_setting") or {}
                rewards.append(
                    {
                        "id": reward["id"],
                        "title": reward["title"],
                        "cost": reward["cost"],
                        "is_enabled": bool(reward.get("is_enabled", True)),
                        "is_paused": bool(reward.get("is_paused", False)),
                        "is_in_stock": bool(reward.get("is_in_stock", True)),
                        "should_redemptions_skip_request_queue": bool(
                            reward.get("should_redemptions_skip_request_queue", False)
                        ),
                        "max_per_stream": (
                            int(stream_limit.get("max_per_stream", 0))
                            if stream_limit.get("is_enabled")
                            else None
                        ),
                        "max_per_user_per_stream": (
                            int(user_limit.get("max_per_user_per_stream", 0))
                            if user_limit.get("is_enabled")
                            else None
                        ),
                    }
                )
            return rewards

        except Exception:
            LOGGER.exception("Error getting custom rewards for broadcaster %s", broadcaster_id)
            return []

    async def get_vips(self, broadcaster_id: str, access_token: str) -> list[dict]:
        """Fetch a complete VIP snapshot or fail without returning partial data."""
        results: list[dict] = []
        cursor: str | None = None
        while True:
            params = {"broadcaster_id": broadcaster_id, "first": 100}
            if cursor:
                params["after"] = cursor
            response = await self._helix_get("channels/vips", params, token=access_token)
            if response is None or response.status_code != 200:
                LOGGER.warning("Complete VIP snapshot failed for broadcaster %s", broadcaster_id)
                raise RuntimeError("Twitch VIP snapshot unavailable")
            body = response.json()
            results.extend(body.get("data", []))
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor:
                return results

    async def remove_vip(self, broadcaster_id: str, user_id: str, access_token: str) -> None:
        """Remove one VIP from a channel or fail without exposing Twitch details."""
        try:
            response = await self._http.delete(
                f"{HELIX_BASE}/channels/vips",
                params={"broadcaster_id": broadcaster_id, "user_id": user_id},
                headers=self._app_headers(access_token),
            )
        except Exception:
            LOGGER.warning("Twitch VIP removal request failed for broadcaster %s", broadcaster_id)
            raise RuntimeError("Twitch VIP removal failed") from None
        if response.status_code != 204:
            LOGGER.warning(
                "Twitch VIP removal rejected for broadcaster %s with status %s",
                broadcaster_id,
                response.status_code,
            )
            raise RuntimeError("Twitch VIP removal failed")

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
                LOGGER.error(f"Failed to fetch videos: user={user_id}")
                return []

            return cast(list[dict], response.json().get("data", []))

        except Exception:
            LOGGER.exception("Error getting videos for user %s", user_id)
            return []

    async def get_channel_badges(self, broadcaster_id: str) -> dict:
        """Fetch channel badge data for subscriber and founder badges.

        Returns ``subscriber_1m`` / ``founder`` (1x URL) for backward compatibility,
        plus ``sets`` containing all versions with all three image sizes.
        """
        _empty: dict = {
            "subscriber_1m": None,
            "founder": None,
            "sets": {"subscriber": [], "founder": [], "bits": []},
        }
        try:
            response = await self._helix_get("chat/badges", {"broadcaster_id": broadcaster_id})
            if not response or response.status_code != 200:
                return _empty

            result: dict = {**_empty, "sets": {k: [] for k in _empty["sets"]}}
            for badge_set in response.json().get("data", []):
                set_id = badge_set.get("set_id")
                versions: list[dict] = badge_set.get("versions", [])
                if not versions or set_id not in ("subscriber", "founder", "bits"):
                    continue

                rich = [
                    {
                        "id": v.get("id", ""),
                        "title": v.get("title", ""),
                        "image_url_1x": v.get("image_url_1x"),
                        "image_url_2x": v.get("image_url_2x"),
                        "image_url_4x": v.get("image_url_4x"),
                    }
                    for v in versions
                ]
                result["sets"][set_id] = rich

                if set_id == "subscriber":
                    # Version "1" is 1-month; fall back to "0" or first
                    v = next((v for v in versions if v.get("id") == "1"), None)
                    if v is None:
                        v = next((v for v in versions if v.get("id") == "0"), versions[0])
                    result["subscriber_1m"] = v.get("image_url_1x")
                elif set_id == "founder":
                    result["founder"] = versions[0].get("image_url_1x")

            return result
        except Exception:
            LOGGER.exception("Error fetching channel badges")
            return _empty

    async def get_global_badges(self) -> dict[str, list[dict]]:
        """Fetch Twitch global badge sets (moderator, broadcaster, vip, etc.).

        Returns a dict keyed by set_id, each value is a list of versions
        with id, title, and all three image sizes.
        """
        try:
            response = await self._helix_get("chat/badges/global")
            if not response or response.status_code != 200:
                return {}

            result: dict[str, list[dict]] = {}
            for badge_set in response.json().get("data", []):
                set_id = badge_set.get("set_id")
                versions: list[dict] = badge_set.get("versions", [])
                if not set_id or not versions:
                    continue
                result[set_id] = [
                    {
                        "id": v.get("id", ""),
                        "title": v.get("title", ""),
                        "image_url_1x": v.get("image_url_1x"),
                        "image_url_2x": v.get("image_url_2x"),
                        "image_url_4x": v.get("image_url_4x"),
                    }
                    for v in versions
                ]
            return result
        except Exception:
            LOGGER.exception("Error fetching global badges")
            return {}

    # ------------------------------------------------------------------
    # Emotes
    # ------------------------------------------------------------------

    async def get_global_emotes(self) -> list[dict]:
        """Fetch Twitch global emotes (usable by everyone in any chat)."""
        try:
            response = await self._helix_get("chat/emotes/global")
            if not response or response.status_code != 200:
                return []
            return [
                {
                    "id": e["id"],
                    "name": e["name"],
                    "url": e.get("images", {}).get("url_2x")
                    or e.get("images", {}).get("url_1x", ""),
                }
                for e in response.json().get("data", [])
            ]
        except Exception:
            LOGGER.exception("Error fetching global emotes")
            return []

    async def get_channel_emotes(self, broadcaster_id: str) -> list[dict]:
        """Fetch emotes belonging to a channel (follower, subscriber, bits tiers)."""
        try:
            response = await self._helix_get("chat/emotes", {"broadcaster_id": broadcaster_id})
            if not response or response.status_code != 200:
                return []
            return [
                {
                    "id": e["id"],
                    "name": e["name"],
                    "url": (
                        f"https://static-cdn.jtvnw.net/emoticons/v2/{e['id']}/animated/dark/2.0"
                        if "animated" in e.get("format", [])
                        else e.get("images", {}).get("url_2x")
                        or e.get("images", {}).get("url_1x", "")
                    ),
                    "emote_type": e.get("emote_type", ""),
                    "tier": e.get("tier", ""),
                    "animated": "animated" in e.get("format", []),
                }
                for e in response.json().get("data", [])
            ]
        except Exception:
            LOGGER.exception("Error fetching channel emotes for %s", broadcaster_id)
            return []

    async def get_user_emotes(
        self, broadcaster_id: str, user_token: str, user_id: str
    ) -> list[dict]:
        """Fetch ALL emotes the authenticated user (bot) can use anywhere on Twitch.

        Requires the bot's user access token. Returns global emotes plus every
        channel emote unlocked via the bot's subscriptions PLATFORM-WIDE, not just
        in *broadcaster_id*'s channel — subscription emotes are usable in any chat
        once unlocked. *broadcaster_id* only asks Twitch to additionally include
        that channel's follower emotes if the bot qualifies. Cursor-paginated:
        a bot subscribed to many channels can exceed one page.

        `owner_id` is kept on each item (not just id/name/url/emote_type) so
        callers can group entries by their originating channel.
        """
        try:
            raw = await self._fetch_paginated(
                "chat/emotes/user",
                {"user_id": user_id, "broadcaster_id": broadcaster_id},
                token=user_token,
            )
            return [
                {
                    "id": e["id"],
                    "name": e["name"],
                    "url": e.get("images", {}).get("url_2x")
                    or e.get("images", {}).get("url_1x", ""),
                    "emote_type": e.get("emote_type", "globals"),
                    "owner_id": e.get("owner_id", ""),
                }
                for e in raw
            ]
        except Exception:
            LOGGER.exception("Error fetching user emotes for broadcaster %s", broadcaster_id)
            return []

    async def is_user_subscribed(self, broadcaster_id: str, user_token: str, user_id: str) -> bool:
        """Whether the authenticated user (bot) holds a real subscription to a channel.

        Uses Check User Subscription (requires ``user:read:subscriptions`` on the
        user token). Authoritative where emote-availability is not: a channel emote
        the bot unlocked via channel points appears usable but is NOT a
        subscription, and this endpoint correctly reports such cases as not
        subscribed (404). Returns False on 404, missing scope (401), or any error.
        """
        try:
            response = await self._helix_get(
                "subscriptions/user",
                {"broadcaster_id": broadcaster_id, "user_id": user_id},
                token=user_token,
            )
            if response and response.status_code == 200:
                return bool(response.json().get("data"))
            return False
        except Exception:
            LOGGER.exception("Error checking subscription for broadcaster %s", broadcaster_id)
            return False
