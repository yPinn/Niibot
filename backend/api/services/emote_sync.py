"""Shared helpers for bot emote availability and enabled_emotes syncing.

Single source of truth for:
- deciding whether the bot can use a given channel emote (availability rule), and
- persisting the available set into ai_settings.enabled_emotes + notifying the bot.

Used by both the per-channel AI settings router and the owner-only admin
aggregate/resync endpoints so the two never drift apart.
"""

from __future__ import annotations

import json
import logging

import asyncpg

from shared.repositories.ai_settings import AISettingsRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


async def notify_config_change(
    pool: asyncpg.Pool, channel_id: str, table: str = "ai_settings"
) -> None:
    """Emit a pg_notify so the bot process invalidates its cached config."""
    payload = json.dumps({"channel_id": channel_id, "table": table})
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_notify('config_change', $1)", payload)


def is_emote_available(emote: dict, accessible: set[str] | None) -> bool:
    """Whether the bot can currently use this emote.

    Global emotes are always usable. When the bot's accessible-emote set is
    known (user token present), a channel emote is usable iff its id appears in
    that set. Without a bot token we can only safely assume follower emotes.
    """
    if emote.get("emote_type") == "globals":
        return True
    if accessible is not None:
        return emote["id"] in accessible
    return emote.get("emote_type") == "follower"


def available_emote_names(
    channel_raw: list[dict], global_raw: list[dict], accessible: set[str] | None
) -> list[str]:
    """Names the bot can use: available channel emotes first, then all globals."""
    channel_names = [e["name"] for e in channel_raw if is_emote_available(e, accessible)]
    global_names = [e["name"] for e in global_raw]
    return channel_names + global_names


async def sync_enabled_emotes(
    pool: asyncpg.Pool, channel_id: str, available_names: list[str]
) -> bool:
    """Persist available emote names into enabled_emotes if they changed.

    Returns True when a write + notify occurred, False when already in sync.
    """
    repo = AISettingsRepository(pool)
    current = await repo.get(channel_id)
    if set(current.get("enabled_emotes") or []) == set(available_names):
        return False
    await repo.upsert(channel_id, enabled_emotes=available_names)
    await notify_config_change(pool, channel_id)
    LOGGER.info(
        "Channel %s: synced %d available emotes -> enabled_emotes",
        channel_id,
        len(available_names),
    )
    return True
