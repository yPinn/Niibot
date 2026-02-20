"""Timer service — business-logic layer for timer configurations."""

from __future__ import annotations

import logging
from dataclasses import asdict

import asyncpg

from shared.repositories.timer import TimerConfigRepository

logger = logging.getLogger(__name__)

VALID_MIN_ROLES = {"everyone", "subscriber", "vip", "moderator", "broadcaster"}


class TimerService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = TimerConfigRepository(pool)

    async def list_timers(self, channel_id: str) -> list[dict]:
        configs = await self.repo.list_all(channel_id)
        return [asdict(cfg) for cfg in configs]

    async def create_timer(
        self,
        channel_id: str,
        timer_name: str,
        *,
        interval_seconds: int,
        min_lines: int,
        message_template: str,
    ) -> dict:
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        if min_lines < 0:
            raise ValueError("min_lines must be non-negative")
        cfg = await self.repo.upsert(
            channel_id,
            timer_name,
            interval_seconds=interval_seconds,
            min_lines=min_lines,
            message_template=message_template,
            enabled=True,
        )
        return asdict(cfg)

    async def update_timer(
        self,
        channel_id: str,
        timer_name: str,
        *,
        interval_seconds: int | None = None,
        min_lines: int | None = None,
        message_template: str | None = None,
        enabled: bool | None = None,
    ) -> dict:
        if interval_seconds is not None and interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        if min_lines is not None and min_lines < 0:
            raise ValueError("min_lines must be non-negative")
        cfg = await self.repo.upsert(
            channel_id,
            timer_name,
            interval_seconds=interval_seconds,
            min_lines=min_lines,
            message_template=message_template,
            enabled=enabled,
        )
        return asdict(cfg)

    async def toggle_timer(self, channel_id: str, timer_name: str, enabled: bool) -> dict:
        cfg = await self.repo.upsert(channel_id, timer_name, enabled=enabled)
        return asdict(cfg)

    async def delete_timer(self, channel_id: str, timer_name: str) -> bool:
        return await self.repo.delete(channel_id, timer_name)
