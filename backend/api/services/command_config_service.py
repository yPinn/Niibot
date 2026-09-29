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
    BUILTIN_INTEGRATIONS,
    BUILTIN_MAP,
    BUILTIN_PREVIEWS,
    BUILTIN_USAGE,
    COMMAND_RESERVED_NAMES,
    COMMAND_RESERVED_OWNERS,
    PUBLIC_DESCRIPTIONS,
)
from shared.errors import ConflictError
from shared.repositories.command_config import (
    UNSET as _UNSET,
)
from shared.repositories.command_config import (
    CommandConfigRepository,
    CommandNamespaceConflictError,
    RedemptionConfigRepository,
    UnsetType,
)
from shared.repositories.message_trigger import MessageTriggerRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

_VIEWER_ROLES = frozenset({"everyone", "subscriber", "vip"})
_BUILTIN_ORDER = {defn["command_name"]: index for index, defn in enumerate(BUILTIN_DEFS)}


class CommandNameConflictError(ConflictError):
    code = "COMMAND.NAME_CONFLICT"
    user_message = "這個指令名稱已被保留，請換一個"


def _normalise_command_name(value: str) -> str:
    return value.strip().lstrip("!").lower()


def _normalise_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    return list(
        dict.fromkeys(_normalise_command_name(alias) for alias in value.split(",") if alias.strip())
    )


def _config_namespace(configs) -> set[str]:
    names: set[str] = set()
    for cfg in configs:
        names.add(cfg.command_name.lower())
        names.update(_normalise_aliases(cfg.aliases))
    return names


def _reserved_conflicts(
    names: set[str], *, current_command: str | None = None, current_is_builtin: bool = False
) -> set[str]:
    conflicts: set[str] = set()
    for name in names & COMMAND_RESERVED_NAMES:
        owner = COMMAND_RESERVED_OWNERS[name]
        if not current_is_builtin or owner != current_command:
            conflicts.add(name)
    return conflicts


def _custom_reserved_conflicts(config, aliases: str | None = None) -> set[str]:
    if config.command_type != "custom":
        return set()
    effective_aliases = config.aliases if aliases is None else aliases
    return _reserved_conflicts(
        {config.command_name.lower(), *_normalise_aliases(effective_aliases)}
    )


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
            "integration_kind": "internal",
            "integration_label": "自訂回覆",
            "capability_requirements": [],
            "external_conditions": [],
        }

    audience = BUILTIN_AUDIENCES[command_name]
    preview = BUILTIN_PREVIEWS[command_name]
    integration = BUILTIN_INTEGRATIONS[command_name]
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
        "integration_kind": integration["kind"],
        "integration_label": integration["label"],
        "capability_requirements": integration["requirements"],
        "external_conditions": integration["conditions"],
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
    ) -> dict | None:
        """Update a command config and return it with usage count."""
        current = await self.cmd_repo.get_config(channel_id, command_name)
        if current is None:
            return None

        if enabled is True:
            namespace_conflicts = _custom_reserved_conflicts(current, aliases)
            if namespace_conflicts:
                raise CommandNameConflictError(context={"names": sorted(namespace_conflicts)})

        normalised_aliases = aliases
        if aliases is not None:
            alias_list = _normalise_aliases(aliases)
            requested_aliases = set(alias_list)
            reserved = _reserved_conflicts(
                requested_aliases,
                current_command=current.command_name,
                current_is_builtin=current.command_type == "builtin",
            )
            if reserved:
                raise CommandNameConflictError(context={"names": sorted(reserved)})

            other_configs = [
                cfg
                for cfg in await self.cmd_repo.list_configs(channel_id)
                if cfg.command_name != current.command_name
            ]
            conflicts = requested_aliases & _config_namespace(other_configs)
            if conflicts:
                raise CommandNameConflictError(context={"names": sorted(conflicts)})
            normalised_aliases = ",".join(alias_list)

        try:
            cfg = await self.cmd_repo.upsert_config(
                channel_id,
                command_name,
                enabled=enabled,
                custom_response=custom_response,
                cooldown=cooldown,
                min_role=min_role,
                aliases=normalised_aliases,
            )
        except CommandNamespaceConflictError as exc:
            raise CommandNameConflictError(context=exc.context) from exc
        return _serialize_command(cfg)

    async def toggle_command(self, channel_id: str, command_name: str, enabled: bool) -> dict:
        """Toggle a command's enabled state."""
        if enabled:
            current = await self.cmd_repo.get_config(channel_id, command_name)
            conflicts = _custom_reserved_conflicts(current) if current else set()
            if conflicts:
                raise CommandNameConflictError(context={"names": sorted(conflicts)})
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
        name = _normalise_command_name(command_name)
        alias_list = _normalise_aliases(aliases)
        requested_names = {name, *alias_list}
        reserved = _reserved_conflicts(requested_names)
        if reserved:
            raise CommandNameConflictError(context={"names": sorted(reserved)})

        taken = _config_namespace(await self.cmd_repo.list_configs(channel_id))
        conflicts = requested_names & taken
        if conflicts:
            raise CommandNameConflictError(context={"names": sorted(conflicts)})

        cfg = await self.cmd_repo.try_insert_config(
            channel_id,
            name,
            command_type="custom",
            enabled=True,
            custom_response=custom_response,
            cooldown=cooldown,
            min_role=min_role,
            aliases=",".join(alias_list) or None,
        )
        if cfg is None:
            raise CommandNameConflictError(context={"names": [name]})
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
            and not _custom_reserved_conflicts(cfg)
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
