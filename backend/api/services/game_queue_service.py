"""Game queue service — business-logic layer for game queue operations."""

from __future__ import annotations

import logging
from dataclasses import asdict

import asyncpg

from shared.repositories.game_queue import GameQueueRepository, GameQueueSettingsRepository

logger = logging.getLogger(__name__)


class GameQueueService:
    """API-facing game queue operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.queue_repo = GameQueueRepository(pool)
        self.settings_repo = GameQueueSettingsRepository(pool)

    @staticmethod
    def _compute_batches(entries: list[dict], group_size: int) -> tuple[list[dict], list[dict]]:
        """Slice entries into current and next batches with 1-indexed positions."""
        for i, entry in enumerate(entries):
            entry["position"] = i + 1
            entry["batch"] = (i // group_size) + 1
        current = entries[:group_size]
        next_batch = entries[group_size : group_size * 2]
        return current, next_batch

    async def get_queue_state(self, channel_id: str) -> dict:
        """Get the full queue state including settings and batches."""
        settings = await self.settings_repo.get_or_create(channel_id)
        entries = await self.queue_repo.get_active_entries(channel_id)
        entry_dicts = [asdict(e) for e in entries]

        current, next_batch = self._compute_batches(entry_dicts, settings.group_size)

        return {
            "current_batch": current,
            "next_batch": next_batch,
            "full_queue": entry_dicts,
            "group_size": settings.group_size,
            "enabled": settings.enabled,
            "total_active": len(entries),
        }

    async def get_public_state(self, channel_id: str) -> dict:
        """Get minimal queue state for OBS overlay (no auth)."""
        settings = await self.settings_repo.get_or_create(channel_id)
        entries = await self.queue_repo.get_active_entries(channel_id)
        entry_dicts = [asdict(e) for e in entries]

        current, next_batch = self._compute_batches(entry_dicts, settings.group_size)

        return {
            "current_batch": current,
            "next_batch": next_batch,
            "group_size": settings.group_size,
            "enabled": settings.enabled,
            "total_active": len(entries),
        }

    async def advance_batch(self, channel_id: str) -> dict:
        """Complete current batch and return new state."""
        settings = await self.settings_repo.get_or_create(channel_id)
        entries = await self.queue_repo.get_active_entries(channel_id)

        to_complete = entries[: settings.group_size]
        if to_complete:
            entry_ids = [e.id for e in to_complete]
            await self.queue_repo.complete_batch(channel_id, entry_ids)

        return await self.get_queue_state(channel_id)

    async def remove_player(self, channel_id: str, entry_id: int) -> dict:
        """Remove a single player and return new state."""
        await self.queue_repo.remove_entry(entry_id, channel_id, "kicked")
        return await self.get_queue_state(channel_id)

    async def clear_queue(self, channel_id: str) -> dict:
        """Clear entire queue and return new state."""
        cleared = await self.queue_repo.clear_queue(channel_id)
        state = await self.get_queue_state(channel_id)
        state["cleared_count"] = cleared
        return state

    async def get_settings(self, channel_id: str) -> dict:
        """Get queue settings."""
        settings = await self.settings_repo.get_or_create(channel_id)
        return asdict(settings)

    async def update_settings(
        self,
        channel_id: str,
        *,
        group_size: int | None = None,
        enabled: bool | None = None,
    ) -> dict:
        """Update queue settings."""
        settings = await self.settings_repo.update_settings(
            channel_id, group_size=group_size, enabled=enabled
        )
        return asdict(settings)
