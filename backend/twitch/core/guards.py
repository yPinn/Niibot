"""Shared command guards: enabled check, role check, cooldown tracking."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol

from twitchio.ext import commands

from shared.models.channel import Channel
from shared.models.command_config import CommandConfig
from shared.repositories.channel import ChannelRepository
from shared.repositories.command_config import CommandConfigRepository


class _HasCooldown(Protocol):
    cooldown: int | None


LOGGER = logging.getLogger("CommandGuard")

# In-memory cooldown tracker (reset on bot restart)
# key: "{channel_id}:{command_name}"
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


def is_on_cooldown(
    channel_id: str,
    command_name: str,
    config: _HasCooldown,
    channel: Channel | None = None,
) -> bool:
    """Check if command is on cooldown.

    Uses command-level override if set, otherwise falls back to channel default.
    """
    effective_cd = (
        config.cooldown
        if config.cooldown is not None
        else (channel.default_cooldown if channel else 0)
    )
    if effective_cd <= 0:
        return False

    key = f"{channel_id}:{command_name}"
    last = _cooldown_tracker.get(key)
    if last and (datetime.now() - last).total_seconds() < effective_cd:
        return True

    return False


def record_cooldown(channel_id: str, command_name: str) -> None:
    """Record cooldown timestamp after successful command execution."""
    _cooldown_tracker[f"{channel_id}:{command_name}"] = datetime.now()


async def check_command(
    repo: CommandConfigRepository,
    ctx: commands.Context,
    command_name: str,
    channel_repo: ChannelRepository | None = None,
) -> CommandConfig | None:
    """Check if command is enabled, role-permitted, and not on cooldown.

    Returns the CommandConfig if all checks pass, or None to skip execution.
    """
    channel_id = ctx.channel.id

    try:
        config = await repo.get_config(channel_id, command_name)
    except Exception as e:
        LOGGER.warning(f"DB error fetching config '{command_name}': {type(e).__name__}: {e}")
        return None

    if not config or not config.enabled:
        return None

    if not has_role(ctx.chatter, config.min_role):
        return None

    # Fetch channel defaults for cooldown fallback
    try:
        channel = await channel_repo.get_channel(channel_id) if channel_repo else None
    except Exception as e:
        LOGGER.warning(f"DB error fetching channel {channel_id}: {type(e).__name__}: {e}")
        channel = None

    if is_on_cooldown(channel_id, command_name, config, channel):
        return None

    record_cooldown(channel_id, command_name)
    return config
