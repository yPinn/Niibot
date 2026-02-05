"""Channel management service — thin business-logic layer.

All SQL operations are delegated to ``ChannelRepository``.
This service adds API-specific formatting and cross-concern
orchestration (e.g. sync_empty_names combines repo + Twitch API).
"""

import logging

import asyncpg

from shared.repositories.channel import ChannelRepository

from .twitch_api import TwitchAPIClient

logger = logging.getLogger(__name__)


class ChannelService:
    """API-facing channel / token / discord-user operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = ChannelRepository(pool)

    # ==================== Channel Status ====================

    async def get_channel_status(self, user_id: str) -> dict:
        """Get channel status formatted for the API response."""
        try:
            channel = await self.repo.get_channel(user_id)
            if channel and channel.enabled:
                return {
                    "subscribed": True,
                    "channel_id": channel.channel_id,
                    "channel_name": channel.channel_name,
                }
            return {
                "subscribed": False,
                "channel_id": user_id,
                "channel_name": channel.channel_name if channel else "",
            }
        except Exception as e:
            logger.exception(f"Error getting channel status for user {user_id}: {e}")
            return {
                "subscribed": False,
                "channel_id": user_id,
                "channel_name": "",
            }

    async def toggle_channel(self, channel_id: str, enabled: bool) -> bool:
        """Enable or disable a channel."""
        try:
            await self.repo.update_channel_enabled(channel_id, enabled)
            action = "enabled" if enabled else "disabled"
            logger.debug(f"Channel {channel_id} {action}")
            return True
        except Exception as e:
            logger.exception(f"Error toggling channel {channel_id}: {e}")
            return False

    async def get_enabled_channels(self) -> list[dict]:
        """Get all enabled channels as dicts (API format)."""
        try:
            channels = await self.repo.list_enabled_channels()
            return [
                {"channel_id": ch.channel_id, "channel_name": ch.channel_name} for ch in channels
            ]
        except Exception as e:
            logger.exception(f"Error getting enabled channels: {e}")
            return []

    # ==================== Token ====================

    async def get_user_token(self, user_id: str) -> str | None:
        """Get the raw access token string for a user."""
        try:
            token_obj = await self.repo.get_token(user_id)
            return token_obj.token if token_obj else None
        except Exception as e:
            logger.exception(f"Error getting token for user {user_id}: {e}")
            return None

    async def get_token_with_refresh(self, user_id: str, twitch_api: TwitchAPIClient) -> str | None:
        """
        Get user's access token, refreshing if expired.

        This method:
        1. Fetches the stored token
        2. Validates it with Twitch
        3. If invalid, attempts refresh using stored refresh_token
        4. Updates database with new tokens on successful refresh

        Returns:
            Valid access token or None if unavailable/refresh failed.
        """
        try:
            token_obj = await self.repo.get_token(user_id)
            if not token_obj:
                logger.warning(f"No token found for user: {user_id}")
                return None

            # Validate current token
            is_valid = await twitch_api.validate_token(token_obj.token)
            if is_valid:
                return token_obj.token

            # Token expired, try refresh
            if not token_obj.refresh:
                logger.warning(f"Token expired and no refresh token for user: {user_id}")
                return None

            logger.info(f"Token expired for user {user_id}, attempting refresh...")
            result = await twitch_api.refresh_access_token(token_obj.refresh)

            if not result.success:
                logger.error(f"Token refresh failed for user {user_id}: {result.error}")
                return None

            # Update database with new tokens
            await self.repo.upsert_token_only(
                user_id=user_id,
                token=result.access_token,
                refresh=result.refresh_token or token_obj.refresh,
            )
            logger.info(f"Token refreshed successfully for user: {user_id}")
            return result.access_token

        except Exception as e:
            logger.exception(f"Error getting token with refresh for user {user_id}: {e}")
            return None

    async def save_token(
        self, user_id: str, access_token: str, refresh_token: str, username: str = ""
    ) -> bool:
        """Save or update a user's OAuth token (+ ensure channel row)."""
        try:
            await self.repo.upsert_token(user_id, access_token, refresh_token, username)
            logger.info(f"Successfully synced token and channel for: {username} ({user_id})")
            return True
        except Exception as e:
            logger.exception(f"Error in save_token transaction: {e}")
            return False

    # ==================== Discord User ====================

    async def save_discord_user(
        self,
        user_id: str,
        username: str,
        display_name: str | None = None,
        avatar: str | None = None,
    ) -> bool:
        """Save or update Discord user info."""
        try:
            await self.repo.upsert_discord_user(user_id, username, display_name, avatar)
            logger.debug(f"Discord user saved: {username} ({user_id})")
            return True
        except Exception as e:
            logger.exception(f"Error saving Discord user to database: {e}")
            return False

    async def get_discord_user(self, user_id: str) -> dict[str, str] | None:
        """Get Discord user info formatted for the API response."""
        try:
            user = await self.repo.get_discord_user(user_id)
            if not user:
                return None
            avatar_url = self._get_discord_avatar_url(user.user_id, user.avatar)
            return {
                "id": user.user_id,
                "name": user.username,
                "display_name": user.display_name or user.username,
                "avatar": avatar_url,
            }
        except Exception as e:
            logger.exception(f"Error getting Discord user {user_id}: {e}")
            return None

    # ==================== Business Logic ====================

    async def sync_empty_names(self, twitch_api: TwitchAPIClient) -> None:
        """Fetch display names from Twitch API for channels with empty names."""
        try:
            empty_channels = await self.repo.list_empty_name_channels()
            if not empty_channels:
                logger.debug("No empty channel names to sync.")
                return

            logger.info(f"Found {len(empty_channels)} channels with empty names. Starting sync...")

            for ch in empty_channels:
                try:
                    user_info = await twitch_api.get_user_info(ch.channel_id)
                    if user_info:
                        new_name = (
                            user_info.get("display_name")
                            or user_info.get("login")
                            or user_info.get("name")
                        )
                        if new_name:
                            await self.repo.update_channel_name(ch.channel_id, new_name)
                            logger.info(
                                f"Successfully updated name for {ch.channel_id} to {new_name}"
                            )
                except Exception as api_err:
                    logger.error(f"Failed to fetch info for channel {ch.channel_id}: {api_err}")
                    continue

        except Exception as e:
            logger.exception(f"Error during sync_empty_names: {e}")

    # ==================== Helpers ====================

    @staticmethod
    def _get_discord_avatar_url(user_id: str, avatar_hash: str | None) -> str:
        """Generate Discord avatar CDN URL."""
        if avatar_hash:
            ext = "gif" if avatar_hash.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}"
        default_avatar_index = int(user_id) % 5
        return f"https://cdn.discordapp.com/embed/avatars/{default_avatar_index}.png"
