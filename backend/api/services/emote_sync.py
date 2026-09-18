"""Shared helpers for bot emote availability and enabled_emotes syncing.

Single source of truth for:
- resolving WHICH bot account currently speaks for a channel (per-channel,
  falling back to the system default — must stay in lockstep with the Twitch
  runtime's own resolver at backend/twitch/core/bot_resolver.py),
- fetching that account's emote availability from Twitch, and
- persisting the available set into ai_settings.enabled_emotes + notifying the bot.

Used by the shared channel emotes endpoint and the owner-only admin
aggregate/resync endpoints so none of them drift apart.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import asyncpg
from pydantic import BaseModel

from services.twitch_api import TwitchAPIClient
from shared.repositories.ai_settings import AISettingsRepository
from shared.repositories.channel import ChannelRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


class EmoteItem(BaseModel):
    id: str
    name: str
    url: str
    emote_type: str = "globals"
    tier: str = ""
    available: bool = True
    animated: bool = False


class OtherChannelEmotes(BaseModel):
    """Emotes the bot account has unlocked on a DIFFERENT channel — e.g. a
    subscription emote, usable anywhere on Twitch once unlocked. Not limited
    to channels Niibot itself monitors; the bot account may be subscribed
    somewhere it was never installed."""

    channel_id: str
    channel_name: str
    display_name: str
    avatar: str
    emotes: list[EmoteItem]


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


async def sync_enabled_emotes_background(
    pool: asyncpg.Pool, channel_id: str, available_names: list[str]
) -> None:
    """`sync_enabled_emotes`, safe to run via `BackgroundTasks.add_task`.

    A background task's exception is otherwise silently swallowed by
    Starlette without even a log line — this makes the failure visible while
    still never surfacing to the response that already returned.
    """
    try:
        await sync_enabled_emotes(pool, channel_id, available_names)
    except Exception:
        LOGGER.exception("emote_sync_failed")


async def sync_enabled_emotes(
    pool: asyncpg.Pool, channel_id: str, available_names: list[str]
) -> bool:
    """Persist available emote names into enabled_emotes if they changed.

    Returns True when a write + notify occurred, False when already in sync.

    Phase 3 extension point: once the bot-account switch executor exists, it
    must call this (via fetch_channel_emotes -> available_emote_names) for the
    NEW active account right after a switch commits — enabled_emotes is a
    single channel-scoped column, so until that call it still holds the
    *previous* account's usable set.
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


# ---------------------------------------------------------------------------
# Per-channel bot account resolution
# ---------------------------------------------------------------------------


async def resolve_bot_id(pool: asyncpg.Pool, channel_id: str, *, system_bot_id: str) -> str:
    """The Twitch account currently speaking for this channel.

    No row, or a NULL active_bot_user_id, means "use the system default" —
    this must stay identical to BotAccountResolver's semantics in
    backend/twitch/core/bot_resolver.py (the Twitch runtime's own resolver,
    which this API process cannot import since it's a separate process).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT active_bot_user_id FROM channel_bot_settings WHERE channel_id = $1",
            channel_id,
        )
    active = row["active_bot_user_id"] if row else None
    return active or system_bot_id


async def resolve_bot_ids(
    pool: asyncpg.Pool, channel_ids: Sequence[str], *, system_bot_id: str
) -> dict[str, str]:
    """Bulk version of resolve_bot_id — one query instead of one per channel."""
    if not channel_ids:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT channel_id, active_bot_user_id FROM channel_bot_settings "
            "WHERE channel_id = ANY($1::text[]) AND active_bot_user_id IS NOT NULL",
            list(channel_ids),
        )
    overrides = {r["channel_id"]: r["active_bot_user_id"] for r in rows}
    return {cid: overrides.get(cid, system_bot_id) for cid in channel_ids}


async def bot_tokens_for(pool: asyncpg.Pool, bot_ids: Iterable[str]) -> dict[str, str | None]:
    """One `get_token` per DISTINCT bot id — multiple channels may share one account."""
    repo = ChannelRepository(pool)
    tokens: dict[str, str | None] = {}
    for bot_id in set(bot_ids):
        token_obj = await repo.get_token(bot_id, "bot")
        tokens[bot_id] = token_obj.token if token_obj else None
    return tokens


# ---------------------------------------------------------------------------
# Twitch fetch + EmoteItem building
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmoteFetch:
    channel_id: str
    channel_raw: list[dict]
    global_raw: list[dict]
    # Full platform-wide response from get_user_emotes — not just the id set
    # used for `accessible` — so callers can recover which OTHER channels the
    # bot has unlocked emotes on. Empty when there's no bot token.
    user_raw: list[dict]
    accessible: set[str] | None
    bot_id: str
    bot_token_available: bool


async def fetch_channel_emotes(
    twitch: TwitchAPIClient,
    channel_id: str,
    *,
    bot_id: str,
    bot_token: str | None,
    include_global: bool = True,
) -> EmoteFetch:
    """Fetch a channel's emotes plus the resolved bot account's accessible set."""
    coros: list = [twitch.get_channel_emotes(channel_id)]
    if include_global:
        coros.append(twitch.get_global_emotes())
    if bot_token:
        coros.append(twitch.get_user_emotes(channel_id, bot_token, bot_id))

    results = await asyncio.gather(*coros)
    channel_raw: list[dict] = results[0]
    idx = 1
    global_raw: list[dict] = []
    if include_global:
        global_raw = results[idx]
        idx += 1
    user_raw: list[dict] = []
    accessible: set[str] | None = None
    if bot_token:
        user_raw = results[idx]
        accessible = {e["id"] for e in user_raw}

    return EmoteFetch(
        channel_id=channel_id,
        channel_raw=channel_raw,
        global_raw=global_raw,
        user_raw=user_raw,
        accessible=accessible,
        bot_id=bot_id,
        bot_token_available=bot_token is not None,
    )


def to_emote_items(fetch: EmoteFetch, *, include_global: bool = True) -> list[EmoteItem]:
    items = [
        EmoteItem(
            id=e["id"],
            name=e["name"],
            url=e["url"],
            emote_type=e.get("emote_type", ""),
            tier=e.get("tier", ""),
            available=is_emote_available(e, fetch.accessible),
            animated=e.get("animated", False),
        )
        for e in fetch.channel_raw
    ]
    if include_global:
        items += [
            EmoteItem(
                id=e["id"],
                name=e["name"],
                url=e["url"],
                emote_type="globals",
                available=True,
                animated=e.get("animated", False),
            )
            for e in fetch.global_raw
        ]
    return items


# ---------------------------------------------------------------------------
# Other-channel emotes — unlocked by the bot account platform-wide
# ---------------------------------------------------------------------------


def other_channel_emote_ids(fetch: EmoteFetch) -> dict[str, list[dict]]:
    """Group `user_raw` entries by owning channel, excluding globals and the
    current channel's own emotes (those are already covered by
    `to_emote_items`/`fetch.channel_raw`)."""
    channel_emote_ids = {e["id"] for e in fetch.channel_raw}
    groups: dict[str, list[dict]] = {}
    for e in fetch.user_raw:
        owner_id = e.get("owner_id") or ""
        if not owner_id or owner_id == fetch.channel_id:
            continue
        if e.get("emote_type") == "globals":
            continue
        if e["id"] in channel_emote_ids:
            continue
        groups.setdefault(owner_id, []).append(e)
    return groups


async def build_other_channel_groups(
    twitch: TwitchAPIClient, fetch: EmoteFetch
) -> list[OtherChannelEmotes]:
    """Resolve channel names/avatars for other_channel_emote_ids() and build
    the response groups. A channel whose user info can't be resolved is
    dropped (logged) rather than failing the whole request."""
    groups = other_channel_emote_ids(fetch)
    if not groups:
        return []

    users = await twitch.get_users_by_ids(list(groups.keys()))
    user_map = {u["id"]: u for u in users}

    result: list[OtherChannelEmotes] = []
    for owner_id, raw_emotes in groups.items():
        user = user_map.get(owner_id)
        if not user:
            LOGGER.warning("build_other_channel_groups: no user info for owner_id=%s", owner_id)
            continue
        result.append(
            OtherChannelEmotes(
                channel_id=owner_id,
                channel_name=user.get("login", ""),
                display_name=user.get("display_name", ""),
                avatar=user.get("profile_image_url", ""),
                emotes=[
                    EmoteItem(
                        id=e["id"],
                        name=e["name"],
                        url=e["url"],
                        emote_type=e.get("emote_type", ""),
                        tier=e.get("tier", ""),
                        available=True,
                        animated=e.get("animated", False),
                    )
                    for e in raw_emotes
                ],
            )
        )

    result.sort(key=lambda g: g.channel_name)
    return result
