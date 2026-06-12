"""Constants and pure helpers for the events cog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord

# Per-guild message cache size: bounded so a busy guild can't evict another's.
_PER_GUILD_CACHE_SIZE = 500
# Skip-delete IDs: TTL-bounded so an ID whose delete never arrives is reclaimed.
_SKIP_IDS_MAX = 1000
_SKIP_IDS_TTL = 300  # seconds

# Times are sourced in UTC and displayed in GMT+8, matching the bot-wide
# convention (see social_preview/_embeds.py, birthday/constants.py).
_TZ_GMT8 = timezone(timedelta(hours=8))


def _fmt_local(dt: datetime) -> str:
    """Format a UTC datetime as a GMT+8 wall-clock string (no tz label)."""
    return dt.astimezone(_TZ_GMT8).strftime("%Y-%m-%d %H:%M:%S")


def _top_role_color(member: discord.Member) -> tuple[int, int, int] | None:
    """Return the member's top coloured role as an RGB tuple, or None."""
    for role in reversed(member.roles):
        if role.color.value:
            return (role.color.r, role.color.g, role.color.b)
    return None
