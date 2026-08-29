"""PG NOTIFY handlers and cache refresh mixin.

Depends on attributes defined in Bot.__init__:
    self._bot_id, self.owner_id, self.subs, self.sessions
    self.channels, self.command_configs, self.redemption_configs
    self.timer_configs, self.message_trigger_configs
Uses self._ch() defined on Bot.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import twitchio

from core.config import get_settings

LOGGER: logging.Logger = logging.getLogger(__name__)


class _NotifyMixin:
    if TYPE_CHECKING:
        # Defined on Bot; declared here so mypy resolves the mixin's calls.
        def _ch(self, channel_id: str) -> str: ...

    async def _seed_and_warm_channel(self, channel_id: str) -> int:
        """Seed redemption + event config defaults and warm the command cache
        for a newly-subscribed channel. Returns the warmed-config count
        (0 on failure, which is logged rather than raised).
        """
        try:
            await self.redemption_configs.ensure_defaults(  # type: ignore[attr-defined]
                channel_id,
                owner_id=self.owner_id,  # type: ignore[attr-defined]
            )
            await self.event_configs.ensure_defaults(channel_id)  # type: ignore[attr-defined]
            return await self.command_configs.warm_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"[NOTIFY] Failed to seed/warm {self._ch(channel_id)}: {e}")
            return 0

    # ------------------------------------------------------------------
    # PG NOTIFY handlers
    # ------------------------------------------------------------------

    async def _handle_channel_toggle(self, connection, pid, channel, payload) -> None:
        try:
            LOGGER.debug(f"[NOTIFY] Notification on '{channel}': {payload}")

            data = json.loads(payload)
            channel_id = data["channel_id"]
            enabled = data["enabled"]

            if channel_id == self._bot_id:  # type: ignore[attr-defined]
                LOGGER.debug(f"[NOTIFY] Ignoring toggle for bot's own channel: {channel_id}")
                return

            LOGGER.info(
                f"[NOTIFY] Processing channel toggle: "
                f"{self._ch(channel_id)} -> {'ENABLE' if enabled else 'DISABLE'}"  # type: ignore[attr-defined]
            )

            if enabled:
                if not self.subs.is_subscribed(channel_id):  # type: ignore[attr-defined]
                    await self.subs.subscribe(channel_id)  # type: ignore[attr-defined]
                    await self._check_bot_mod_status(channel_id)  # type: ignore[attr-defined]

                    # Scope check: mod check catches expired tokens (401/403) but a valid
                    # token with missing scopes would pass mod check and never enter
                    # _needs_reauth. Read stored scopes from DB as a safety net.
                    if channel_id not in self._needs_reauth:  # type: ignore[attr-defined]
                        token_obj = await self.channels.get_token(channel_id)  # type: ignore[attr-defined]
                        if token_obj and token_obj.scopes:
                            from shared.twitch_scopes import missing_broadcaster_scopes

                            if missing_broadcaster_scopes(token_obj.scopes.split()):
                                await self._mark_reauth_required(channel_id)
                                LOGGER.warning(
                                    f"[NOTIFY] {self._ch(channel_id)} missing broadcaster scopes"  # type: ignore[attr-defined]
                                    " after channel toggle — marking for reauth"
                                )

                    count = await self._seed_and_warm_channel(channel_id)
                    LOGGER.info(
                        f"[NOTIFY] Warmed cache: {count} configs for {self._ch(channel_id)}"
                    )
                    await self._send_welcome_message(channel_id)  # type: ignore[attr-defined]
                    LOGGER.info(f"[NOTIFY] Instantly subscribed to channel: {self._ch(channel_id)}")  # type: ignore[attr-defined]
                else:
                    LOGGER.info(
                        f"[NOTIFY] Channel {self._ch(channel_id)} already subscribed, skipping"
                    )  # type: ignore[attr-defined]
            else:
                if self.subs.is_subscribed(channel_id):  # type: ignore[attr-defined]
                    await self.subs.unsubscribe(channel_id)  # type: ignore[attr-defined]
                    self._bot_is_mod.discard(channel_id)  # type: ignore[attr-defined]
                    LOGGER.info(
                        f"[NOTIFY] Instantly unsubscribed from channel: {self._ch(channel_id)}"
                    )  # type: ignore[attr-defined]
                else:
                    LOGGER.info(f"[NOTIFY] Channel {self._ch(channel_id)} not subscribed, skipping")  # type: ignore[attr-defined]

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling channel toggle notification: {e}")

    async def _mark_reauth_required(self, user_id: str) -> None:
        """Add to in-memory set AND persist the flag to DB so the API forces re-login."""
        self._needs_reauth.add(user_id)  # type: ignore[attr-defined]
        try:
            await self.channels.mark_requires_reauth(user_id)  # type: ignore[attr-defined]
        except Exception:
            LOGGER.warning(f"[NOTIFY] Failed to persist requires_reauth for {self._ch(user_id)}")  # type: ignore[attr-defined]

    async def _send_welcome_message(self, channel_id: str) -> None:
        """Send a one-line welcome message when the bot is enabled for a channel."""
        if not get_settings().is_production:
            return
        try:
            users = await self.fetch_users(ids=[channel_id])  # type: ignore[attr-defined]
            if not users:
                return
            await users[0].send_message(
                message="帽子叔叔正在巡邏...",
                sender=self._bot_id,  # type: ignore[attr-defined]
            )
            LOGGER.info(f"[NOTIFY] Welcome message sent to channel {self._ch(channel_id)}")  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(
                f"[NOTIFY] Failed to send welcome message to {self._ch(channel_id)}: {e}"
            )  # type: ignore[attr-defined]

    async def _send_reauth_restored_message(self, channel_id: str, login: str) -> None:
        """Notify chat that bot functionality has been restored after reauth."""
        if not get_settings().is_production:
            return
        try:
            users = await self.fetch_users(ids=[channel_id])  # type: ignore[attr-defined]
            if not users:
                return
            await users[0].send_message(
                message="帽子叔叔回來上班了！",
                sender=self._bot_id,  # type: ignore[attr-defined]
            )
            LOGGER.info(
                f"[NOTIFY] Reauth restored message sent to {login} ({self._ch(channel_id)})"
            )  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(
                f"[NOTIFY] Failed to send reauth restored message to {self._ch(channel_id)}: {e}"
            )  # type: ignore[attr-defined]

    async def _handle_new_token(self, connection, pid, channel, payload) -> None:
        try:
            data = json.loads(payload)
            user_id = data["user_id"]
            LOGGER.info(
                f"[NOTIFY] Received new token notification for user_id: {self._ch(user_id)}"
            )  # type: ignore[attr-defined]

            if user_id == self._bot_id:  # type: ignore[attr-defined]
                LOGGER.debug(f"[NOTIFY] Ignoring new token for bot's own account: {user_id}")
                return

            token_obj = await self.channels.get_token(user_id)  # type: ignore[attr-defined]
            if not token_obj:
                LOGGER.warning(f"[NOTIFY] Token not found for user_id: {self._ch(user_id)}")  # type: ignore[attr-defined]
                return

            try:
                user_info = await self.add_token(token_obj.token, token_obj.refresh)  # type: ignore[attr-defined]
                LOGGER.info(f"[NOTIFY] Loaded token for new user: {user_info.login} ({user_id})")

                from shared.twitch_scopes import missing_broadcaster_scopes

                missing = missing_broadcaster_scopes(user_info.scopes)
                if missing:
                    LOGGER.warning(f"[NOTIFY] {user_info.login} missing scopes: {missing}")
                    await self._mark_reauth_required(user_id)
                else:
                    was_reauth = user_id in self._needs_reauth  # type: ignore[attr-defined]
                    self._needs_reauth.discard(user_id)  # type: ignore[attr-defined]
                    if was_reauth:
                        await self._send_reauth_restored_message(user_id, user_info.login or "")  # type: ignore[attr-defined]
                        # Re-verify mod status: _bot_is_mod may be empty if the token was
                        # already expired at startup (mod check returned 401 before now).
                        await self._check_bot_mod_status(user_id)  # type: ignore[attr-defined]

                await self.add_channel_to_db(user_id, user_info.login or "unknown")  # type: ignore[attr-defined]

                # Admission gate: only join channels whose owner is approved.
                # channels.enabled is driven by memberships.status (migration
                # 084); a pending/suspended owner has enabled=FALSE, so we load
                # the token but do not subscribe. Approval flips enabled, which
                # fires channel_toggle → _handle_channel_toggle subscribes then.
                channel = await self.channels.get_channel(user_id)  # type: ignore[attr-defined]
                if not channel or not channel.enabled:
                    LOGGER.info(
                        f"[NOTIFY] Channel {self._ch(user_id)} not enabled "  # type: ignore[attr-defined]
                        "(awaiting admission) — token loaded, not subscribing"
                    )
                    return

                if not self.subs.is_subscribed(user_id):  # type: ignore[attr-defined]
                    await self.subs.subscribe(user_id)  # type: ignore[attr-defined]
                    await self._check_bot_mod_status(user_id)  # type: ignore[attr-defined]

                    count = await self._seed_and_warm_channel(user_id)
                    LOGGER.info(f"[NOTIFY] Warmed cache: {count} configs for {self._ch(user_id)}")

                    try:
                        await self.sessions.ensure_session(user_id)  # type: ignore[attr-defined]
                    except Exception as e:
                        LOGGER.warning(f"[NOTIFY] Failed to check live status for {user_id}: {e}")

                    LOGGER.info(f"[NOTIFY] Instantly subscribed to new channel: {user_id}")

            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(f"[NOTIFY] Invalid token for new user {user_id}: {e}")
                await self._mark_reauth_required(user_id)

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling new token notification: {e}")

    async def _handle_token_reauth(self, connection, pid, channel, payload) -> None:
        """Bust the in-process token cache after a broadcaster re-authorizes."""
        try:
            data = json.loads(payload)
            user_id = data["user_id"]
            if user_id == self._bot_id:  # type: ignore[attr-defined]
                return

            from shared.repositories.channel import _token_cache

            _token_cache.invalidate(f"token:{user_id}:broadcaster")
            LOGGER.info(
                f"[NOTIFY] token_reauth for {self._ch(user_id)} — cache busted, re-checking"  # type: ignore[attr-defined]
            )
            await self._handle_new_token(connection, pid, channel, payload)
        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling token_reauth: {e}")

    async def _handle_config_change(self, connection, pid, channel, payload) -> None:
        """Reload in-memory cache for the affected channel on config writes."""
        try:
            data = json.loads(payload)
            channel_id = data.get("channel_id")
            table = data.get("table", "")

            # Global module_config changes have no channel_id — invalidate global cache.
            if table == "module_config":
                from shared.repositories.module_config import _CACHE_KEY, _module_config_cache

                _module_config_cache.invalidate(_CACHE_KEY)
                LOGGER.info("[NOTIFY] module_config updated, global pack cache invalidated")
                return

            if not channel_id or not self.subs.is_subscribed(channel_id):  # type: ignore[attr-defined]
                return

            LOGGER.info(
                f"[NOTIFY] Config change on {table} for {self._ch(channel_id)}, refreshing cache"
            )  # type: ignore[attr-defined]
            await self._refresh_channel_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"[NOTIFY] Error handling config_change: {e}")

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def _refresh_channel_cache(self, channel_id: str) -> None:
        """Reload all config caches for a single channel from DB."""
        from shared.repositories.ai_settings import _ai_settings_cache
        from shared.repositories.channel import _channel_cache, _enabled_channels_cache
        from shared.repositories.command_config import _redemption_cache
        from shared.repositories.event_config import (
            EVENT_TYPES,
        )
        from shared.repositories.event_config import (
            _config_cache as _evt_cache,
        )
        from shared.repositories.event_config import (
            _config_list_cache as _evt_list_cache,
        )

        def _invalidate_channel() -> None:
            _channel_cache.invalidate(f"channel:{channel_id}")
            _enabled_channels_cache.clear()

        def _invalidate_events() -> None:
            for et in EVENT_TYPES:
                _evt_cache.invalidate(f"event_config:{channel_id}:{et}")
            _evt_list_cache.invalidate(f"event_list:{channel_id}")

        ops: list[tuple[str, object]] = [
            ("commands", self.command_configs.warm_cache(channel_id)),  # type: ignore[attr-defined]
            ("channel", _invalidate_channel),
            ("events", _invalidate_events),
            (
                "redemptions",
                lambda: _redemption_cache.invalidate_prefix(f"redemption:{channel_id}:"),
            ),
            ("timers", lambda: self.timer_configs.invalidate_cache(channel_id)),  # type: ignore[attr-defined]
            ("triggers", lambda: self.message_trigger_configs.invalidate_cache(channel_id)),  # type: ignore[attr-defined]
            ("ai_settings", lambda: _ai_settings_cache.invalidate(f"ai_settings:{channel_id}")),
        ]
        for name, op in ops:
            try:
                result = op() if callable(op) else op  # type: ignore[operator]
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                LOGGER.warning(f"Cache refresh ({name}) failed for {channel_id}: {e}")

    async def _periodic_cache_refresh(self) -> None:
        """Safety net: reload all config caches every 5 minutes.

        Catches any pg_notify misses (e.g. LISTEN connection dropped).
        """
        while True:
            try:
                subscribed = self.subs.subscribed  # type: ignore[attr-defined]
                for channel_id in subscribed:
                    await self._refresh_channel_cache(channel_id)  # type: ignore[attr-defined]
                LOGGER.debug(f"Periodic cache refresh complete for {len(subscribed)} channels")
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Periodic cache refresh error: {e}")
            await asyncio.sleep(300)
