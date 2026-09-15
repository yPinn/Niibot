"""Timer service — business-logic layer for timer configurations."""

from __future__ import annotations

import logging
from dataclasses import asdict

import asyncpg

from shared.builtin_timers import BUILTIN_TIMERS
from shared.repositories.timer import TimerConfigRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


class TimerService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = TimerConfigRepository(pool)

    async def _upsert(self, channel_id: str, timer_name: str, **kwargs) -> dict:
        """Wrap repo.upsert(); translate the alias-uniqueness violation into a
        ValueError the router already maps to a clean 400 (TimerInvalidError).

        timers_channel_alias_unique (channel_id, command_alias) is a separate
        constraint from the upsert's own ON CONFLICT (channel_id, timer_name)
        target, so a duplicate alias raises a raw UniqueViolationError instead
        of being handled by that clause.
        """
        try:
            cfg = await self.repo.upsert(channel_id, timer_name, **kwargs)
        except asyncpg.exceptions.UniqueViolationError as e:
            if e.constraint_name == "timers_channel_alias_unique":
                alias = kwargs.get("command_alias")
                raise ValueError(f"別名 !{alias} 已經被其他計時器使用了") from e
            raise
        return asdict(cfg)

    async def list_timers(self, channel_id: str) -> list[dict]:
        configs = await self.repo.list_all(channel_id)
        result = [asdict(cfg) for cfg in configs]

        db_names = {cfg.timer_name for cfg in configs}
        for bt in BUILTIN_TIMERS:
            if bt.timer_name not in db_names:
                result.append(
                    {
                        "id": None,
                        "channel_id": channel_id,
                        "timer_name": bt.timer_name,
                        "interval_seconds": bt.interval_seconds,
                        "min_lines": bt.min_lines,
                        "message_template": bt.message_template,
                        "enabled": True,
                        "announce": bt.announce,
                        "command_alias": None,
                        "builtin": True,
                        "created_at": None,
                        "updated_at": None,
                    }
                )

        return result

    async def create_timer(
        self,
        channel_id: str,
        timer_name: str,
        *,
        interval_seconds: int,
        min_lines: int,
        message_template: str,
        announce: bool = False,
        command_alias: str | None = None,
    ) -> dict:
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        if min_lines < 0:
            raise ValueError("min_lines must be non-negative")
        return await self._upsert(
            channel_id,
            timer_name,
            interval_seconds=interval_seconds,
            min_lines=min_lines,
            message_template=message_template,
            enabled=True,
            announce=announce,
            command_alias=command_alias,
        )

    async def update_timer(
        self,
        channel_id: str,
        timer_name: str,
        *,
        interval_seconds: int | None = None,
        min_lines: int | None = None,
        message_template: str | None = None,
        enabled: bool | None = None,
        announce: bool | None = None,
        command_alias: str | None = None,
        clear_alias: bool = False,
    ) -> dict:
        if interval_seconds is not None and interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        if min_lines is not None and min_lines < 0:
            raise ValueError("min_lines must be non-negative")
        return await self._upsert(
            channel_id,
            timer_name,
            interval_seconds=interval_seconds,
            min_lines=min_lines,
            message_template=message_template,
            enabled=enabled,
            announce=announce,
            command_alias=command_alias,
            clear_alias=clear_alias,
        )

    async def toggle_timer(self, channel_id: str, timer_name: str, enabled: bool) -> dict:
        cfg = await self.repo.upsert(channel_id, timer_name, enabled=enabled)
        return asdict(cfg)

    async def delete_timer(self, channel_id: str, timer_name: str) -> bool:
        return await self.repo.delete(channel_id, timer_name)
