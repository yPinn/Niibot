"""Command config service — business-logic layer for command and redemption configurations."""

import logging
from dataclasses import asdict

import asyncpg

from shared.repositories.command_config import CommandConfigRepository, RedemptionConfigRepository

logger = logging.getLogger(__name__)

BUILTIN_DESCRIPTIONS: dict[str, str] = {
    "hi": "打招呼",
    "help": "列出可用指令",
    "uptime": "顯示開播時間",
    "ai": "AI 回答問題",
    "運勢": "今日運勢占卜",
    "rk": "TFT 排行榜查詢",
}


class CommandConfigService:
    """API-facing command & redemption config operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.cmd_repo = CommandConfigRepository(pool)
        self.redemption_repo = RedemptionConfigRepository(pool)

    # ---- Command configs ----

    async def list_commands(self, channel_id: str) -> list[dict]:
        """Get command configs with usage counts from command_stats."""
        configs = await self.cmd_repo.ensure_defaults(channel_id)
        counts = await self._get_command_usage_counts(channel_id)
        return [
            {**asdict(cfg), "usage_count": counts.get(f"!{cfg.command_name}", 0)} for cfg in configs
        ]

    async def update_command(
        self,
        channel_id: str,
        command_name: str,
        *,
        enabled: bool | None = None,
        custom_response: str | None = None,
        cooldown: int | None = None,
        min_role: str | None = None,
        aliases: str | None = None,
    ) -> dict:
        """Update a command config and return it with usage count."""
        cfg = await self.cmd_repo.upsert_config(
            channel_id,
            command_name,
            enabled=enabled,
            custom_response=custom_response,
            cooldown=cooldown,
            min_role=min_role,
            aliases=aliases,
        )
        counts = await self._get_command_usage_counts(channel_id)
        return {**asdict(cfg), "usage_count": counts.get(f"!{cfg.command_name}", 0)}

    async def toggle_command(self, channel_id: str, command_name: str, enabled: bool) -> dict:
        """Toggle a command's enabled state."""
        cfg = await self.cmd_repo.upsert_config(channel_id, command_name, enabled=enabled)
        counts = await self._get_command_usage_counts(channel_id)
        return {**asdict(cfg), "usage_count": counts.get(f"!{cfg.command_name}", 0)}

    async def create_custom_command(
        self,
        channel_id: str,
        command_name: str,
        *,
        custom_response: str | None = None,
        cooldown: int | None = None,
        min_role: str = "everyone",
        aliases: str | None = None,
    ) -> dict:
        """Create a new custom command."""
        cfg = await self.cmd_repo.upsert_config(
            channel_id,
            command_name,
            command_type="custom",
            enabled=True,
            custom_response=custom_response,
            cooldown=cooldown,
            min_role=min_role,
            aliases=aliases,
        )
        return {**asdict(cfg), "usage_count": 0}

    async def delete_custom_command(self, channel_id: str, command_name: str) -> bool:
        """Delete a custom command. Returns True if deleted."""
        return await self.cmd_repo.delete_config(channel_id, command_name)

    async def _get_command_usage_counts(self, channel_id: str) -> dict[str, int]:
        """Sum usage_count per command_name across all sessions."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT command_name, SUM(usage_count)::int as total "
                "FROM command_stats WHERE channel_id = $1 GROUP BY command_name",
                channel_id,
            )
            return {row["command_name"]: row["total"] for row in rows}

    # ---- Public commands ----

    async def list_public_commands(self, channel_id: str) -> list[dict]:
        """Get enabled commands for a channel by channel_id."""
        configs = await self.cmd_repo.ensure_defaults(channel_id)
        return [
            {
                "name": f"!{cfg.command_name}",
                "description": (
                    BUILTIN_DESCRIPTIONS.get(cfg.command_name, cfg.custom_response or "")
                    if cfg.command_type == "builtin"
                    else cfg.custom_response or ""
                ),
                "min_role": cfg.min_role,
            }
            for cfg in configs
            if cfg.enabled
        ]

    # ---- Redemption configs ----

    async def list_redemptions(self, channel_id: str) -> list[dict]:
        """Get redemption configs."""
        configs = await self.redemption_repo.ensure_defaults(channel_id)
        return [asdict(cfg) for cfg in configs]

    async def update_redemption(
        self,
        channel_id: str,
        action_type: str,
        reward_name: str,
        enabled: bool,
    ) -> dict:
        """Update a redemption config."""
        cfg = await self.redemption_repo.upsert_config(
            channel_id, action_type, reward_name, enabled
        )
        return asdict(cfg)
