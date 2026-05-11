"""Shared command guards: enabled check, role check, cooldown tracking."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol

from twitchio.ext import commands

from shared.models.channel import Channel
from shared.models.command_config import CommandConfig
from shared.repositories.channel import ChannelRepository
from shared.repositories.command_config import CommandConfigRepository


class _HasCooldown(Protocol):
    cooldown: int | None


LOGGER: logging.Logger = logging.getLogger(__name__)

# In-memory cooldown tracker — key: "{channel_id}:{command_name}"
_cooldown_tracker: dict[str, datetime] = {}
_cooldown_call_count: int = 0
_EVICT_INTERVAL = 500

ROLE_HIERARCHY = ["everyone", "subscriber", "vip", "moderator", "broadcaster"]

MIN_COOLDOWN = 5  # seconds — system-wide floor, cannot be overridden per-channel


def has_role(chatter, min_role: str) -> bool:
    """Check if chatter meets the minimum role requirement."""
    if min_role == "everyone":
        return True

    min_level = ROLE_HIERARCHY.index(min_role) if min_role in ROLE_HIERARCHY else 0

    if chatter.broadcaster:
        return True
    if chatter.moderator:
        return ROLE_HIERARCHY.index("moderator") >= min_level
    if chatter.vip:
        return ROLE_HIERARCHY.index("vip") >= min_level
    if chatter.subscriber:
        return ROLE_HIERARCHY.index("subscriber") >= min_level

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
    raw_cd = (
        config.cooldown
        if config.cooldown is not None
        else (channel.default_cooldown if channel else 0)
    )
    if raw_cd <= 0:
        return False
    effective_cd = max(MIN_COOLDOWN, raw_cd)

    key = f"{channel_id}:{command_name}"
    last = _cooldown_tracker.get(key)
    if last and (datetime.now(UTC) - last).total_seconds() < effective_cd:
        return True

    return False


def record_cooldown(channel_id: str, command_name: str) -> None:
    """Record cooldown timestamp after successful command execution."""
    global _cooldown_call_count
    _cooldown_tracker[f"{channel_id}:{command_name}"] = datetime.now(UTC)
    _cooldown_call_count += 1
    if _cooldown_call_count >= _EVICT_INTERVAL:
        _cooldown_call_count = 0
        _evict_cooldowns()


def _evict_cooldowns() -> None:
    """Remove entries older than 1 hour to prevent unbounded growth."""
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    stale = [k for k, v in _cooldown_tracker.items() if v < cutoff]
    for k in stale:
        del _cooldown_tracker[k]


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

    try:
        channel = await channel_repo.get_channel(channel_id) if channel_repo else None
    except Exception as e:
        LOGGER.warning(f"DB error fetching channel {channel_id}: {type(e).__name__}: {e}")
        channel = None

    if is_on_cooldown(channel_id, command_name, config, channel):
        return None

    record_cooldown(channel_id, command_name)
    return config
