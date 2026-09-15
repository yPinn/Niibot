"""Command config service — business-logic layer for command and redemption configurations."""

import logging
from dataclasses import asdict

import asyncpg

from core.config import get_settings
from shared.builtin_commands import (
    BUILTIN_AUDIENCES,
    BUILTIN_CATEGORIES,
    BUILTIN_DEFS,
    BUILTIN_DESCRIPTIONS,
    BUILTIN_DETAILS,
    BUILTIN_MAP,
    BUILTIN_PREVIEWS,
    BUILTIN_USAGE,
    PUBLIC_DESCRIPTIONS,
)
from shared.repositories.command_config import (
    UNSET as _UNSET,
)
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
    UnsetType,
)
from shared.repositories.message_trigger import MessageTriggerRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

_VIEWER_ROLES = frozenset({"everyone", "subscriber", "vip"})
_BUILTIN_ORDER = {defn["command_name"]: index for index, defn in enumerate(BUILTIN_DEFS)}


def _builtin_category_label(command_type: str, command_name: str) -> str | None:
    """Display label for a builtin command's category; None for custom commands."""
    if command_type != "builtin":
        return None
    defn = BUILTIN_MAP.get(command_name)
    return BUILTIN_CATEGORIES.get(defn.get("category", "")) if defn else None


def _command_metadata(command_type: str, command_name: str, min_role: str) -> dict:
    """Return immutable catalog metadata separately from mutable channel settings."""
    if command_type != "builtin":
        return {
            "description": "",
            "detail": "",
            "usage": f"!{command_name}",
            "preview_input": "",
            "preview_output": "",
            "audience": None,
            "public_visible": min_role in _VIEWER_ROLES,
            "display_order": len(BUILTIN_DEFS),
            "category_label": None,
        }

    audience = BUILTIN_AUDIENCES[command_name]
    preview = BUILTIN_PREVIEWS[command_name]
    return {
        "description": BUILTIN_DESCRIPTIONS[command_name],
        "detail": BUILTIN_DETAILS[command_name],
        "usage": BUILTIN_USAGE[command_name],
        "preview_input": preview["input"],
        "preview_output": preview["output"],
        "audience": audience,
        "public_visible": (
            audience == "viewer"
            and min_role in _VIEWER_ROLES
            and command_name in PUBLIC_DESCRIPTIONS
        ),
        "display_order": _BUILTIN_ORDER[command_name],
        "category_label": _builtin_category_label(command_type, command_name),
    }


def _serialize_command(cfg) -> dict:
    return {
        **asdict(cfg),
        **_command_metadata(cfg.command_type, cfg.command_name, cfg.min_role),
    }


class CommandConfigService:
    """API-facing command & redemption config operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.cmd_repo = CommandConfigRepository(pool)
        self.redemption_repo = RedemptionConfigRepository(pool)

    # ---- Command configs ----

    async def list_commands(self, channel_id: str) -> list[dict]:
        """Get command configs with all-time usage counts from command_configs."""
        configs = await self.cmd_repo.list_configs(channel_id)
        return [_serialize_command(cfg) for cfg in configs]

    async def update_command(
        self,
        channel_id: str,
        command_name: str,
        *,
        enabled: bool | None = None,
        custom_response: str | None = None,
        cooldown: int | None | UnsetType = _UNSET,
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
        return _serialize_command(cfg)

    async def toggle_command(self, channel_id: str, command_name: str, enabled: bool) -> dict:
        """Toggle a command's enabled state."""
        cfg = await self.cmd_repo.upsert_config(channel_id, command_name, enabled=enabled)
        return _serialize_command(cfg)

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
        return _serialize_command(cfg)

    async def delete_custom_command(self, channel_id: str, command_name: str) -> bool:
        """Delete a custom command. Returns True if deleted."""
        return await self.cmd_repo.delete_config(channel_id, command_name)

    # ---- Public commands ----

    async def list_public_commands(self, channel_id: str) -> list[dict]:
        """Get enabled commands and triggers for a channel by channel_id."""
        configs = await self.cmd_repo.list_configs(channel_id)
        commands = [
            {
                "name": f"!{cfg.command_name}",
                "description": (
                    PUBLIC_DESCRIPTIONS[cfg.command_name]
                    if cfg.command_type == "builtin"
                    else cfg.custom_response or ""
                ),
                "min_role": cfg.min_role,
                "command_type": cfg.command_type,
                "category_label": _builtin_category_label(cfg.command_type, cfg.command_name),
            }
            for cfg in configs
            if cfg.enabled
            and cfg.min_role in _VIEWER_ROLES
            and (
                cfg.command_type == "custom"
                or (
                    BUILTIN_AUDIENCES.get(cfg.command_name) == "viewer"
                    and cfg.command_name in PUBLIC_DESCRIPTIONS
                )
            )
        ]
        trigger_configs = await MessageTriggerRepository(self.pool).list_enabled(channel_id)
        triggers = [
            {
                "name": cfg.pattern,
                "description": cfg.response,
                "min_role": cfg.min_role,
                "command_type": "trigger",
            }
            for cfg in trigger_configs
            if cfg.min_role in _VIEWER_ROLES
        ]
        return commands + triggers

    # ---- Redemption configs ----

    async def list_redemptions(self, channel_id: str) -> list[dict]:
        """Get redemption configs.

        Passes owner_id so RedemptionConfigRepository.ensure_defaults seeds the
        niibot_auth row when this channel is the bot owner. The repository's
        in-process `_seeded_redemptions` cache makes the call idempotent —
        subsequent requests skip the INSERT loop entirely.
        """
        configs = await self.redemption_repo.ensure_defaults(
            channel_id, owner_id=str(get_settings().owner_id)
        )
        return [asdict(cfg) for cfg in configs]

    async def update_redemption(
        self,
        channel_id: str,
        action_type: str,
        reward_name: str,
        enabled: bool,
        *,
        reward_id: str | None = None,
    ) -> dict:
        """Update a redemption config."""
        cfg = await self.redemption_repo.upsert_config(
            channel_id,
            action_type,
            reward_name,
            enabled,
            reward_id=reward_id,
        )
        return asdict(cfg)

    async def update_first_settings(
        self, channel_id: str, *, message: str, announce_color: str
    ) -> dict | None:
        """Update the 'first' redemption's custom announcement text/color."""
        cfg = await self.redemption_repo.update_first_settings(
            channel_id, message=message, announce_color=announce_color
        )
        return asdict(cfg) if cfg else None
