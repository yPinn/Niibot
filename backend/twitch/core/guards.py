"""Shared command guards: enabled check, role check, cooldown tracking."""

from __future__ import annotations

import logging
from datetime import datetime

from twitchio.ext import commands

from shared.models.command_config import CommandConfig
from shared.repositories.command_config import CommandConfigRepository

LOGGER = logging.getLogger("CommandGuard")

# In-memory cooldown tracker (reset on bot restart)
# key: "{channel_id}:{command_name}:global" or "{channel_id}:{command_name}:user:{user_id}"
_cooldown_tracker: dict[str, datetime] = {}

# Role hierarchy (higher index = higher privilege)
ROLE_HIERARCHY = ["everyone", "subscriber", "vip", "moderator", "broadcaster"]


def has_role(chatter, min_role: str) -> bool:
    """Check if chatter meets the minimum role requirement."""
    if min_role == "everyone":
        return True

    min_level = ROLE_HIERARCHY.index(min_role) if min_role in ROLE_HIERARCHY else 0

    # Check from highest to lowest
    if chatter.broadcaster:
        return ROLE_HIERARCHY.index("broadcaster") >= min_level
    if chatter.moderator:
        return ROLE_HIERARCHY.index("moderator") >= min_level
    if chatter.vip:
        return ROLE_HIERARCHY.index("vip") >= min_level
    if chatter.subscriber:
        return ROLE_HIERARCHY.index("subscriber") >= min_level

    # everyone level
    return min_level == 0


def is_on_cooldown(channel_id: str, command_name: str, user_id: str, config: CommandConfig) -> bool:
    """Check if command is on cooldown (global or per-user)."""
    now = datetime.now()

    # Check global cooldown
    if config.cooldown_global > 0:
        global_key = f"{channel_id}:{command_name}:global"
        last = _cooldown_tracker.get(global_key)
        if last and (now - last).total_seconds() < config.cooldown_global:
            return True

    # Check per-user cooldown
    if config.cooldown_per_user > 0:
        user_key = f"{channel_id}:{command_name}:user:{user_id}"
        last = _cooldown_tracker.get(user_key)
        if last and (now - last).total_seconds() < config.cooldown_per_user:
            return True

    return False


def record_cooldown(channel_id: str, command_name: str, user_id: str) -> None:
    """Record cooldown timestamps after successful command execution."""
    now = datetime.now()
    _cooldown_tracker[f"{channel_id}:{command_name}:global"] = now
    _cooldown_tracker[f"{channel_id}:{command_name}:user:{user_id}"] = now


async def check_command(
    repo: CommandConfigRepository,
    ctx: commands.Context,
    command_name: str,
) -> CommandConfig | None:
    """Check if command is enabled, role-permitted, and not on cooldown.

    Returns the CommandConfig if all checks pass, or None to skip execution.
    """
    channel_id = ctx.channel.id
    config = await repo.get_config(channel_id, command_name)

    if not config or not config.enabled:
        return None

    if not has_role(ctx.chatter, config.min_role):
        return None

    if is_on_cooldown(channel_id, command_name, ctx.chatter.id, config):
        return None

    record_cooldown(channel_id, command_name, ctx.chatter.id)
    return config
