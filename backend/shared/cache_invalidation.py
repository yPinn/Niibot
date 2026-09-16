"""Pure in-process cache invalidation driven by `config_change`/`channel_toggle`
pg_notify payloads.

Every function here is synchronous and touches only module-level
`AsyncTTLCache` instances — no DB access, no pool dependency. That matters
because the API service's listener (see `api/app.py`) can start before the
DB pool is connected; keeping this module DB-free means invalidation never
blocks on, or fails because of, pool startup.

Both the twitch bot (`twitch/core/_notify_mixin.py`) and the API process
(`api/app.py`) call `invalidate_channel_config()` on NOTIFY. The bot
additionally re-warms `command_configs` from DB afterward — the API doesn't,
since its reads always go back through `@cached` on demand.
"""

from __future__ import annotations

import logging

LOGGER: logging.Logger = logging.getLogger(__name__)


def invalidate_command_caches(channel_id: str) -> None:
    """Invalidate command_config + redemption caches for one channel.

    Must run before any warm-cache step. `warm_cache()` reads through
    `list_configs()`, which is itself `@cached` on `_cmd_list_cache` — skipping
    this would re-warm `_cmd_cache` with stale rows and pin them for another
    TTL cycle. `warm_cache()` also only ever `set`s entries, never clears them,
    so a deleted command/alias would otherwise survive indefinitely.
    """
    from shared.repositories.command_config import _cmd_cache, _cmd_list_cache, _redemption_cache

    _cmd_list_cache.invalidate(f"cmd_list:{channel_id}")
    _cmd_cache.invalidate_prefix(f"cmd_config:{channel_id}:")
    _cmd_cache.invalidate_prefix(f"cmd_alias:{channel_id}:")
    _redemption_cache.invalidate_prefix(f"redemption:{channel_id}:")


def invalidate_channel_caches(channel_id: str) -> None:
    """Invalidate `_channel_cache` / `_enabled_channels_cache` for one channel."""
    from shared.repositories.channel import _channel_cache, _enabled_channels_cache

    _channel_cache.invalidate(f"channel:{channel_id}")
    _enabled_channels_cache.clear()


def invalidate_event_caches(channel_id: str) -> None:
    from shared.repositories.event_config import EVENT_TYPES
    from shared.repositories.event_config import _config_cache as _evt_cache
    from shared.repositories.event_config import _config_list_cache as _evt_list_cache

    for et in EVENT_TYPES:
        _evt_cache.invalidate(f"event_config:{channel_id}:{et}")
    _evt_list_cache.invalidate(f"event_list:{channel_id}")


def invalidate_timer_cache(channel_id: str) -> None:
    from shared.repositories.timer import _timer_list_cache

    _timer_list_cache.invalidate(f"timer_list:{channel_id}")


def invalidate_trigger_cache(channel_id: str) -> None:
    from shared.repositories.message_trigger import _trigger_list_cache

    _trigger_list_cache.invalidate(f"trigger_list:{channel_id}")


def invalidate_ai_settings_cache(channel_id: str) -> None:
    from shared.repositories.ai_settings import _ai_settings_cache

    _ai_settings_cache.invalidate(f"ai_settings:{channel_id}")


def invalidate_module_config() -> None:
    from shared.repositories.module_config import _CACHE_KEY, _module_config_cache

    _module_config_cache.invalidate(_CACHE_KEY)


_CHANNEL_CONFIG_OPS = (
    ("commands", invalidate_command_caches),
    ("channel", invalidate_channel_caches),
    ("events", invalidate_event_caches),
    ("timers", invalidate_timer_cache),
    ("triggers", invalidate_trigger_cache),
    ("ai_settings", invalidate_ai_settings_cache),
)


def invalidate_channel_config(channel_id: str) -> None:
    """Run every per-channel config invalidation op, logging (not raising) per-op failures.

    Shared by the twitch bot's `config_change`/`channel_toggle` NOTIFY handlers
    and the API's own listener.
    """
    for name, op in _CHANNEL_CONFIG_OPS:
        try:
            op(channel_id)
        except Exception as e:
            LOGGER.warning(
                "cache_invalidate_failed",
                extra={
                    "code": "RUNTIME.CACHE_INVALIDATE_FAILED",
                    "event_class": "persistent",
                    "cache_op": name,
                    "channel_id": channel_id,
                    "error": str(e),
                },
            )


def clear_config_caches() -> None:
    """Periodic full-clear safety net for config caches. Does NOT touch `_token_cache`
    (`shared/repositories/channel.py`) — that has its own `new_token`/`token_reauth`
    notify flow and clearing it would force needless token decrypts.

    Correct-by-construction fallback for pg_notify misses: a dropped LISTEN
    connection, or a table with no NOTIFY trigger at all (several config
    tables currently have partial or no trigger coverage). Costs one cold DB
    read per key on next access.
    """
    from shared.repositories.ai_settings import _ai_settings_cache
    from shared.repositories.channel import _channel_cache, _enabled_channels_cache
    from shared.repositories.command_config import _cmd_cache, _cmd_list_cache, _redemption_cache
    from shared.repositories.event_config import _config_cache, _config_list_cache
    from shared.repositories.message_trigger import _trigger_list_cache
    from shared.repositories.module_config import _module_config_cache
    from shared.repositories.timer import _timer_list_cache

    for cache in (
        _cmd_cache,
        _cmd_list_cache,
        _redemption_cache,
        _channel_cache,
        _enabled_channels_cache,
        _config_cache,
        _config_list_cache,
        _timer_list_cache,
        _trigger_list_cache,
        _ai_settings_cache,
        _module_config_cache,
    ):
        cache.clear()
