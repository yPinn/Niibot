"""Event config service — business-logic layer for event configurations."""

import logging
from dataclasses import asdict

import asyncpg

from shared.repositories.event_config import DEFAULT_TEMPLATES, EVENT_TYPES, EventConfigRepository

logger = logging.getLogger(__name__)


class EventConfigService:
    """API-facing event config operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = EventConfigRepository(pool)

    async def list_configs_with_counts(self, channel_id: str) -> list[dict]:
        """Get configs with trigger counts from stream_events."""
        configs = await self.repo.ensure_defaults(channel_id)
        counts = await self._get_trigger_counts(channel_id)
        return [{**asdict(cfg), "trigger_count": counts.get(cfg.event_type, 0)} for cfg in configs]

    async def update_config(
        self,
        channel_id: str,
        event_type: str,
        message_template: str,
        enabled: bool,
    ) -> dict:
        """Update an event config and return it with trigger count."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}")
        cfg = await self.repo.upsert_config(channel_id, event_type, message_template, enabled)
        counts = await self._get_trigger_counts(channel_id)
        return {**asdict(cfg), "trigger_count": counts.get(cfg.event_type, 0)}

    async def toggle_config(self, channel_id: str, event_type: str, enabled: bool) -> dict:
        """Toggle an event config's enabled state."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}")
        # Get existing config first to preserve template
        existing = await self.repo.get_config(channel_id, event_type)
        if existing is None:
            # Ensure defaults exist
            await self.repo.ensure_defaults(channel_id)
            existing = await self.repo.get_config(channel_id, event_type)
        template = existing.message_template if existing else DEFAULT_TEMPLATES.get(event_type, "")
        cfg = await self.repo.upsert_config(channel_id, event_type, template, enabled)
        counts = await self._get_trigger_counts(channel_id)
        return {**asdict(cfg), "trigger_count": counts.get(cfg.event_type, 0)}

    async def _get_trigger_counts(self, channel_id: str) -> dict[str, int]:
        """Count total events per type from stream_events table."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT event_type, COUNT(*) as cnt "
                "FROM stream_events WHERE channel_id = $1 GROUP BY event_type",
                channel_id,
            )
            return {row["event_type"]: row["cnt"] for row in rows}
