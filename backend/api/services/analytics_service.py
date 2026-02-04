"""Analytics service — thin business-logic layer.

All SQL operations are delegated to ``AnalyticsRepository``.
"""

import logging

import asyncpg

from shared.repositories.analytics import AnalyticsRepository

logger = logging.getLogger(__name__)


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
