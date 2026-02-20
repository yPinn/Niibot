"""Command config service — business-logic layer for command and redemption configurations."""

import logging
from dataclasses import asdict

import asyncpg

from shared.repositories.command_config import CommandConfigRepository, RedemptionConfigRepository

logger = logging.getLogger(__name__)

BUILTIN_DESCRIPTIONS: dict[str, str] = {
    "hi": "向聊天室打招呼",
    "help": "顯示所有可用指令列表",
    "uptime": "查看目前已開播多久",
    "ai": "向 AI 提問",
    "tft": "查詢聯盟戰棋排名",
    "運勢": "運勢占卜",
    "tarot": "塔羅牌占卜（可指定感情、事業、財運）",
    "斥責": "頻道反惡意言論聲明",
}

# 公開 /commands 頁面用，包含用法說明供觀眾參考
# 有中文別名的指令，用法示例以中文別名為主
PUBLIC_DESCRIPTIONS: dict[str, str] = {
    "hi": "向聊天室打招呼",
    "help": "顯示所有可用指令列表",
    "uptime": "查看目前已開播多久",
    "ai": "向 AI 提問，用法：!問 <問題>",
    "tft": "查詢聯盟戰棋排名，用法：!tft <玩家名>#<tag>",
    "運勢": "運勢占卜",
    "tarot": "塔羅牌占卜，可指定分類：!塔羅 [感情/事業/財運]",
    "斥責": "頻道反惡意言論聲明",
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
            {
                **asdict(cfg),
                "usage_count": counts.get(f"!{cfg.command_name}", 0),
                "description": BUILTIN_DESCRIPTIONS.get(cfg.command_name, "")
                if cfg.command_type == "builtin"
                else "",
            }
            for cfg in configs
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
        """Get enabled commands and triggers for a channel by channel_id."""
        configs = await self.cmd_repo.ensure_defaults(channel_id)
        commands = [
            {
                "name": f"!{cfg.command_name}",
                "description": (
                    PUBLIC_DESCRIPTIONS.get(cfg.command_name, cfg.custom_response or "")
                    if cfg.command_type == "builtin"
                    else cfg.custom_response or ""
                ),
                "min_role": cfg.min_role,
                "command_type": cfg.command_type,
            }
            for cfg in configs
            if cfg.enabled
        ]
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT pattern, response, min_role FROM message_triggers "
                "WHERE channel_id = $1 AND enabled = TRUE ORDER BY pattern",
                channel_id,
            )
        triggers = [
            {
                "name": row["pattern"],
                "description": row["response"],
                "min_role": row["min_role"],
                "command_type": "trigger",
            }
            for row in rows
        ]
        return commands + triggers

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
