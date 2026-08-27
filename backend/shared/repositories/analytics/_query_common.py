"""Shared module-level constants and helpers for the analytics query mixins.

Split out of _query_mixin.py so every query sub-mixin imports from a single
leaf module (no circular-import risk), and tests have one stable patch target
for _get_bot_list.
"""

from __future__ import annotations

import logging
import time

import httpx

LOGGER = logging.getLogger(__name__)

_TOP_CHATTERS_LIMIT = 10
_TOP_COMMANDS_LIMIT = 10
_SESSION_CHART_LIMIT = 12
_TOP_GAMES_LIMIT = 5

_KNOWN_BOTS: frozenset[str] = frozenset(
    {
        "nightbot",
        "streamlabs",
        "streamelements",
        "moobot",
        "wizebot",
        "fossabot",
        "commanderroot",
        "electricallongboard",
        "sery_bot",
        "soundalerts",
        "pokemoncommunitygame",
        "bingothemighty",
        "kofistreambot",
        "rogueg1rl",
        "stay_hydrated_bot",
        "anotherttvviewer",
        "own3d",
        "pretzel_rocks",
        "streambeats",
        "rainmaker",
        "streamholics",
        "revlobot",
        "botisimo",
        "p0sitivitybot",
        "lurxx",
        "streamloots",
        "fireside_bot",
        "streamcapturebot",
        "staysafe_bot",
        "dinks_bot",
        "marbiebot",
        "dixpermit",
        "playwithviewers",
        "niibot_",
        "chiwabots",
    }
)

_bot_cache: frozenset[str] = frozenset()
_bot_cache_ts: float = 0.0
_BOT_CACHE_TTL: float = 86400.0  # 24 hours


async def _get_bot_list() -> list[str]:
    """Return merged bot list: manual _KNOWN_BOTS + TwitchInsights (cached 24h)."""
    global _bot_cache, _bot_cache_ts
    if _bot_cache and time.monotonic() - _bot_cache_ts < _BOT_CACHE_TTL:
        return list(_KNOWN_BOTS | _bot_cache)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.twitchinsights.net/v1/bots/all")
            resp.raise_for_status()
            data = resp.json()
            _bot_cache = frozenset(entry[0].lower() for entry in data.get("bots", []))
            _bot_cache_ts = time.monotonic()
            LOGGER.info("Fetched %d bots from TwitchInsights", len(_bot_cache))
    except Exception as exc:
        LOGGER.warning("TwitchInsights bot list fetch failed (%s), using local list", exc)
    return list(_KNOWN_BOTS | _bot_cache)


_SCORE_SQL: str = """ROUND((
    (t.watch_seconds::numeric / 3600.0)
    + (1.5 * LN(
        LEAST(
            t.total_messages::numeric,
            GREATEST(10.0, t.watch_seconds::numeric / 30.0)
        ) + 1.0
      ))
    + (0.5 * LN(t.sessions_attended::numeric + 1.0))
    + COALESCE(eb.sub_tier_bonus, 0.0)
    + (2.0 * LN(COALESCE(eb.total_bits, 0)::numeric / 100.0 + 1.0))
) * (1.0 + LEAST(COALESCE(sk.streak_count, 0), 20) * 0.05)
  * CASE
      WHEN t.last_seen >= NOW() - INTERVAL '30 days' THEN 1.0
      WHEN t.last_seen >= NOW() - INTERVAL '60 days' THEN 0.75
      ELSE 0.5
    END
, 2)::float"""

_STREAK_CTE: str = """streak_data AS (
    SELECT user_id, streak_count
    FROM viewer_attendance_streaks
    WHERE channel_id = $1
)"""

_STREAK_CTE_EMPTY: str = (
    "streak_data AS (SELECT NULL::text AS user_id, 0::int AS streak_count WHERE FALSE)"
)
