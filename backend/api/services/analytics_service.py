"""Analytics service — thin business-logic layer.

All SQL operations are delegated to ``AnalyticsRepository``.
"""

import logging
from datetime import datetime

import asyncpg

from shared.repositories.analytics import AnalyticsRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


class AnalyticsService:
    """API-facing analytics read operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = AnalyticsRepository(pool)

    async def get_summary(self, channel_id: str, days: int = 30) -> dict:
        """Get analytics summary for a channel."""
        return await self.repo.get_summary(channel_id, days)

    async def get_session_commands(self, session_id: int, channel_id: str) -> list[dict] | None:
        """Get command stats for a session."""
        return await self.repo.get_session_commands(session_id, channel_id)

    async def get_session_events(self, session_id: int, channel_id: str) -> list[dict] | None:
        """Get events for a session."""
        return await self.repo.get_session_events(session_id, channel_id)

    async def get_top_commands(
        self, channel_id: str, days: int = 30, limit: int = 10
    ) -> list[dict]:
        """Get top commands across all sessions."""
        return await self.repo.list_top_commands(channel_id, days, limit)

    async def get_insights(self, channel_id: str, days: int = 30) -> dict:
        """Get aggregated channel insights."""
        return await self.repo.get_insights(channel_id, days)

    async def list_viewers(self, channel_id: str, days: int = 30, limit: int = 50) -> list[dict]:
        """Get top viewers list."""
        return await self.repo.list_viewers(channel_id, days, limit)

    async def get_viewer_profile(
        self, channel_id: str, user_id: str, days: int = 30
    ) -> dict | None:
        """Get detailed profile for a single viewer."""
        return await self.repo.get_viewer_profile(channel_id, user_id, days)

    async def get_viewer_session_attendance(
        self, channel_id: str, user_id: str, days: int = 30
    ) -> list[dict]:
        """Get per-session attendance data for a viewer."""
        return await self.repo.get_viewer_session_attendance(channel_id, user_id, days)

    async def get_viewer_channel_status(self, channel_id: str, user_id: str) -> dict | None:
        """Get cached EventSub status for a viewer."""
        return await self.repo.get_viewer_channel_status(channel_id, user_id)

    async def bulk_upsert_follow_dates(self, channel_id: str, followers: list[dict]) -> int:
        return await self.repo.bulk_upsert_follow_dates(channel_id, followers)

    async def bulk_upsert_mod_status(self, channel_id: str, mods: list[dict]) -> int:
        return await self.repo.bulk_upsert_mod_status(channel_id, mods)

    async def bulk_upsert_vip_status(self, channel_id: str, vips: list[dict]) -> int:
        return await self.repo.bulk_upsert_vip_status(channel_id, vips)

    async def bulk_upsert_subscribers(self, channel_id: str, subs: list[dict]) -> int:
        return await self.repo.bulk_upsert_subscribers(channel_id, subs)

    async def upsert_viewer_profile_cache(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        profile_image_url: str | None,
        offline_image_url: str | None,
        account_created_at: datetime | None,
        broadcaster_type: str | None,
    ) -> None:
        """Cache Twitch profile fields after a get_user_info call."""
        await self.repo.upsert_viewer_profile_cache(
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            profile_image_url=profile_image_url,
            offline_image_url=offline_image_url,
            account_created_at=account_created_at,
            broadcaster_type=broadcaster_type,
        )
