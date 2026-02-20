"""Message trigger service — business-logic layer for trigger configurations."""

from __future__ import annotations

import logging
from dataclasses import asdict

import asyncpg

from shared.repositories.message_trigger import MessageTriggerRepository

logger = logging.getLogger(__name__)

VALID_MATCH_TYPES = {"contains", "startswith", "exact", "regex"}
VALID_MIN_ROLES = {"everyone", "subscriber", "vip", "moderator", "broadcaster"}


class MessageTriggerService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = MessageTriggerRepository(pool)

    async def list_triggers(self, channel_id: str) -> list[dict]:
        configs = await self.repo.list_all(channel_id)
        return [asdict(cfg) for cfg in configs]

    async def create_trigger(
        self,
        channel_id: str,
        trigger_name: str,
        *,
        match_type: str = "contains",
        pattern: str,
        case_sensitive: bool = False,
        response: str,
        min_role: str = "everyone",
        cooldown: int | None = None,
        priority: int = 0,
    ) -> dict:
        if match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"Invalid match_type: {match_type}")
        if min_role not in VALID_MIN_ROLES:
            raise ValueError(f"Invalid min_role: {min_role}")
        cfg = await self.repo.upsert(
            channel_id,
            trigger_name,
            match_type=match_type,
            pattern=pattern,
            case_sensitive=case_sensitive,
            response=response,
            min_role=min_role,
            cooldown=cooldown,
            priority=priority,
            enabled=True,
        )
        return asdict(cfg)

    async def update_trigger(
        self,
        channel_id: str,
        trigger_name: str,
        *,
        match_type: str | None = None,
        pattern: str | None = None,
        case_sensitive: bool | None = None,
        response: str | None = None,
        min_role: str | None = None,
        cooldown: int | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
    ) -> dict:
        if match_type is not None and match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"Invalid match_type: {match_type}")
        if min_role is not None and min_role not in VALID_MIN_ROLES:
            raise ValueError(f"Invalid min_role: {min_role}")
        cfg = await self.repo.upsert(
            channel_id,
            trigger_name,
            match_type=match_type,
            pattern=pattern,
            case_sensitive=case_sensitive,
            response=response,
            min_role=min_role,
            cooldown=cooldown,
            priority=priority,
            enabled=enabled,
        )
        return asdict(cfg)

    async def toggle_trigger(self, channel_id: str, trigger_name: str, enabled: bool) -> dict:
        cfg = await self.repo.upsert(channel_id, trigger_name, enabled=enabled)
        return asdict(cfg)

    async def delete_trigger(self, channel_id: str, trigger_name: str) -> bool:
        return await self.repo.delete(channel_id, trigger_name)
