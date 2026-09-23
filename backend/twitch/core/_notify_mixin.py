"""PG NOTIFY handlers and cache refresh mixin.

Depends on attributes defined in Bot.__init__:
    self._bot_id, self.owner_id, self.subs, self.sessions, self.bots
    self.channels, self.command_configs, self.redemption_configs
    self.timer_configs, self.message_trigger_configs, self.video_queue
Uses self._ch() and self.sender_for() defined on Bot.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import twitchio

from core.config import get_settings
from shared.assistant import AssistantScopeChange
from shared.cache_invalidation import (
    invalidate_ai_settings_cache,
    invalidate_channel_config,
    invalidate_module_config,
)

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
                    result = await self.subs.subscribe(channel_id)  # type: ignore[attr-defined]
                    if not result.converged:
                        LOGGER.warning(
                            "[NOTIFY] EventSub reconcile incomplete for %s: %s",
                            self._ch(channel_id),
                            result.errors,
                        )
                        return
                    await self._check_bot_mod_status(channel_id)  # type: ignore[attr-defined]

                    # Scope check: mod check catches expired tokens (401/403) but a valid
                    # token with missing scopes would pass mod check and never enter
                    # _needs_reauth. Read stored scopes from DB as a safety net.
                    if channel_id not in self._needs_reauth:  # type: ignore[attr-defined]
                        token_obj = await self.channels.get_token(channel_id)  # type: ignore[attr-defined]
                        if token_obj and token_obj.scopes:
                            from shared.twitch_scopes import missing_broadcaster_core_scopes

                            if missing_broadcaster_core_scopes(token_obj.scopes.split()):
                                await self._mark_reauth_required(
                                    channel_id,
                                    expected_revision=token_obj.credential_revision,
                                )
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
                    LOGGER.info(
                        f"[NOTIFY] Instantly unsubscribed from channel: {self._ch(channel_id)}"
                    )  # type: ignore[attr-defined]
                else:
                    LOGGER.info(f"[NOTIFY] Channel {self._ch(channel_id)} not subscribed, skipping")  # type: ignore[attr-defined]

                # Drop all per-channel in-memory state, not just subscription
                # bookkeeping — otherwise churny tenants (disable/re-enable,
                # or many short-lived channels) leak entries across the
                # process lifetime with nothing to signal it (see
                # shared/gauges.py for the counters that would show this).
                self._bot_is_mod.discard(channel_id)  # type: ignore[attr-defined]
                self._needs_reauth.discard(channel_id)  # type: ignore[attr-defined]
                self._mod_check_pending.discard(channel_id)  # type: ignore[attr-defined]
                self.subs.forget(channel_id)  # type: ignore[attr-defined]
                self._clear_component_channel_memory(channel_id)

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling channel toggle notification: {e}")

    async def _mark_reauth_required(
        self, user_id: str, *, expected_revision: int | None = None
    ) -> None:
        """Add to in-memory set AND persist the flag to DB so the API forces re-login.

        Announces the problem in chat exactly once, at the moment the channel
        newly enters this state — not on a timer. Every other call site that
        keeps hitting the same scope error while already flagged is a no-op
        here; the channel just stays gated (see the message-gate short-circuit
        in Bot._handle_broadcaster_message) until reauth resolves.
        """
        try:
            updated = await self.channels.mark_requires_reauth(  # type: ignore[attr-defined]
                user_id,
                expected_revision=expected_revision,
            )
            if not updated:
                LOGGER.info(
                    "[NOTIFY] Ignoring stale reauth failure for %s at credential revision %s",
                    self._ch(user_id),
                    expected_revision,
                )
                return
            already_flagged = user_id in self._needs_reauth  # type: ignore[attr-defined]
            self._needs_reauth.add(user_id)  # type: ignore[attr-defined]
            if already_flagged:
                return
        except Exception:
            LOGGER.warning(f"[NOTIFY] Failed to persist requires_reauth for {self._ch(user_id)}")  # type: ignore[attr-defined]
            return

        if not get_settings().is_production:
            return
        try:
            from utils.reauth import build_reauth_message

            users = await self.fetch_users(ids=[user_id])  # type: ignore[attr-defined]
            if not users:
                return
            await users[0].send_message(
                message=build_reauth_message(users[0].name or self._ch(user_id)),  # type: ignore[attr-defined]
                sender=self.sender_for(user_id),  # type: ignore[attr-defined]
            )
            LOGGER.info(f"[NOTIFY] Reauth notification sent to {self._ch(user_id)}")  # type: ignore[attr-defined]
        except Exception:
            LOGGER.exception(f"[NOTIFY] Failed to send reauth notification for {self._ch(user_id)}")  # type: ignore[attr-defined]

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
                sender=self.sender_for(channel_id),  # type: ignore[attr-defined]
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
                sender=self.sender_for(channel_id),  # type: ignore[attr-defined]
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
                user_info = await self.add_token(  # type: ignore[attr-defined]
                    token_obj.token,
                    token_obj.refresh,
                    persist=False,
                    expected_user_id=user_id,
                    expected_token_type="broadcaster",
                    expected_revision=token_obj.credential_revision,
                )
                LOGGER.info(f"[NOTIFY] Loaded token for new user: {user_info.login} ({user_id})")

                from shared.twitch_scopes import missing_broadcaster_core_scopes

                missing = missing_broadcaster_core_scopes(user_info.scopes)
                if missing:
                    LOGGER.warning(f"[NOTIFY] {user_info.login} missing scopes: {missing}")
                    await self._mark_reauth_required(
                        user_id,
                        expected_revision=token_obj.credential_revision,
                    )
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
                    result = await self.subs.subscribe(user_id)  # type: ignore[attr-defined]
                    if not result.converged:
                        LOGGER.warning(
                            "[NOTIFY] EventSub reconcile incomplete for %s: %s",
                            self._ch(user_id),
                            result.errors,
                        )
                        return
                    await self._check_bot_mod_status(user_id)  # type: ignore[attr-defined]

                    count = await self._seed_and_warm_channel(user_id)
                    LOGGER.info(f"[NOTIFY] Warmed cache: {count} configs for {self._ch(user_id)}")

                    try:
                        await self.sessions.ensure_session(user_id)  # type: ignore[attr-defined]
                    except Exception as e:
                        LOGGER.warning(f"[NOTIFY] Failed to check live status for {user_id}: {e}")

                    LOGGER.info(f"[NOTIFY] Instantly subscribed to new channel: {user_id}")

            except twitchio.exceptions.InvalidTokenException as e:
                if e.status in {408, 425, 429} or e.status >= 500:
                    LOGGER.warning(
                        "[NOTIFY] Token reload temporarily unavailable for %s (HTTP %s); "
                        "API reconciliation will retry",
                        user_id,
                        e.status,
                    )
                    return
                LOGGER.warning(f"[NOTIFY] Invalid token for new user {user_id}: {e}")
                await self._mark_reauth_required(
                    user_id,
                    expected_revision=token_obj.credential_revision,
                )

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

            if data.get("disconnected"):
                # Credential row is gone — the same transaction's
                # channels.enabled = FALSE already fires channel_toggle,
                # which owns unsubscribe and per-channel state cleanup.
                LOGGER.info(
                    f"[NOTIFY] token_reauth for {self._ch(user_id)} — disconnected, cache busted only"  # type: ignore[attr-defined]
                )
                return

            notified_revision = data.get("credential_revision")
            runtime_revision = getattr(self, "_runtime_credential_revisions", {}).get(user_id)
            if (
                notified_revision is not None
                and runtime_revision == notified_revision
                and not data.get("scopes_changed")
                and not data.get("reauth_cleared")
            ):
                LOGGER.debug(
                    "[NOTIFY] token_reauth for %s revision %s already active; skipping reload",
                    self._ch(user_id),
                    notified_revision,
                )
                return

            if (
                data.get("scopes_changed") or data.get("reauth_cleared")
            ) and self.subs.is_subscribed(user_id):  # type: ignore[attr-defined]
                await self.subs.unsubscribe(user_id)  # type: ignore[attr-defined]
            LOGGER.info(
                f"[NOTIFY] token_reauth for {self._ch(user_id)} — cache busted, re-checking"  # type: ignore[attr-defined]
            )
            await self._handle_new_token(connection, pid, channel, payload)
        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling token_reauth: {e}")

    async def _handle_bot_token_updated(self, connection, pid, channel, payload) -> None:
        """Hot-reload a bot credential after web OAuth — system default or a
        tenant-selected custom account currently active/desired somewhere.

        An authorized-but-never-selected custom account is deliberately left
        unloaded; it only enters the token store once some channel's
        `channel_bot_settings` row makes it relevant (see
        `BotAccountResolver.relevant_bot_ids()`).
        """
        try:
            data = json.loads(payload)
            user_id = data["user_id"]
            if user_id not in self.bots.relevant_bot_ids():  # type: ignore[attr-defined]
                LOGGER.debug("[NOTIFY] Bot credential persisted for not-yet-relevant account")
                return

            from shared.repositories.channel import _token_cache

            _token_cache.invalidate(f"token:{user_id}:bot")
            token_obj = await self.channels.get_token(user_id, "bot")  # type: ignore[attr-defined]
            if token_obj is None:
                LOGGER.error("[NOTIFY] Updated Bot credential is unavailable: %s", user_id)
                return

            await self.add_token(  # type: ignore[attr-defined]
                token_obj.token,
                token_obj.refresh,
                persist=False,
                expected_user_id=user_id,
                expected_token_type="bot",
                expected_revision=token_obj.credential_revision,
            )
            LOGGER.info("[NOTIFY] Bot credential hot reload completed for %s", user_id)
        except Exception:
            LOGGER.exception("[NOTIFY] Bot credential hot reload failed")

    async def _handle_bot_selection_changed(self, connection, pid, channel, payload) -> None:
        """Refresh sender routing after selection, fallback, or tenant unlink."""
        try:
            data = json.loads(payload)
            channel_id = data.get("channel_id")
            if channel_id:
                await self.bots.refresh(channel_id)  # type: ignore[attr-defined]
            else:
                await self.bots.load_all()  # type: ignore[attr-defined]
            LOGGER.info("[NOTIFY] Bot sender selection refreshed")
        except Exception:
            LOGGER.exception("[NOTIFY] Bot sender selection refresh failed")

    async def _handle_config_change(self, connection, pid, channel, payload) -> None:
        """Reload in-memory cache for the affected channel on config writes."""
        try:
            data = json.loads(payload)
            channel_id = data.get("channel_id")
            table = data.get("table", "")

            # Global module_config changes have no channel_id — invalidate global cache.
            if table == "module_config":
                invalidate_module_config()
                LOGGER.info("[NOTIFY] module_config updated, global pack cache invalidated")
                return

            if not channel_id or not self.subs.is_subscribed(channel_id):  # type: ignore[attr-defined]
                return

            LOGGER.info(
                f"[NOTIFY] Config change on {table} for {self._ch(channel_id)}, refreshing cache"
            )  # type: ignore[attr-defined]
            await self._refresh_channel_cache(channel_id)  # type: ignore[attr-defined]
            if data.get("clear_assistant_memory") is True:
                self._clear_component_channel_memory(channel_id)
        except Exception as e:
            LOGGER.warning(f"[NOTIFY] Error handling config_change: {e}")

    async def _handle_assistant_scope_changed(self, connection, pid, channel, payload) -> None:
        """Invalidate assistant settings and retire old scoped conversations."""
        try:
            change = AssistantScopeChange.from_payload(payload)
        except ValueError:
            LOGGER.warning("[NOTIFY] Invalid assistant_scope_changed payload")
            return

        invalidate_ai_settings_cache(change.channel_id)
        self._clear_component_channel_memory_except_scope(
            change.channel_id,
            change.scope.memory_key,
        )
        LOGGER.info(
            "[NOTIFY] Assistant scope changed for %s: mode=%s revision=%s",
            self._ch(change.channel_id),
            change.assistant_mode.value,
            change.active_roleplay_revision_id,
        )

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _clear_component_channel_memory(self, channel_id: str) -> None:
        """Best-effort removal of optional per-channel component state."""
        components = getattr(self, "_components", {})
        for component in components.values():
            hook = getattr(component, "clear_channel_memory", None)
            if not callable(hook):
                continue
            try:
                hook(channel_id)
            except Exception:
                LOGGER.exception("[NOTIFY] Failed to clear component memory for %s", channel_id)

    def _clear_component_channel_memory_except_scope(
        self,
        channel_id: str,
        assistant_scope: str,
    ) -> None:
        """Remove retired assistant identities without clearing duplicate events."""
        components = getattr(self, "_components", {})
        for component in components.values():
            hook = getattr(component, "clear_channel_memory_except_scope", None)
            if not callable(hook):
                continue
            try:
                hook(channel_id, assistant_scope)
            except Exception:
                LOGGER.exception(
                    "[NOTIFY] Failed to retire old component memory for %s",
                    channel_id,
                )

    async def _refresh_channel_cache(self, channel_id: str) -> None:
        """Reload all config caches for a single channel from DB.

        Pure in-memory invalidation is delegated to the shared helper (used
        identically by the API process's own listener, see api/app.py). This
        bot additionally re-warms `command_configs` from DB afterward so
        hot-path chat lookups stay O(1) memory access with zero DB dependency
        — the invalidation above must run first so the warm step can't pin
        stale rows back into the cache (see cache_invalidation.py docstring).
        """
        invalidate_channel_config(channel_id)
        try:
            await self.command_configs.warm_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"Cache refresh (commands) failed for {channel_id}: {e}")

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
