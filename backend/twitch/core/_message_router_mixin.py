"""Message routing mixin — handles message triggers and custom commands.

Depends on attributes defined in Bot.__init__:
    self.bot_id, self.owner_id, self.sessions
    self.command_configs, self.redemption_configs
    self.message_trigger_configs, self.channels
Uses self.sender_for() defined on Bot.
"""

from __future__ import annotations

import asyncio
import logging

import twitchio

from core.guards import has_role, is_on_cooldown, record_cooldown
from shared.trigger_matching import match_trigger
from utils.substitution import substitute_variables as _substitute_variables

LOGGER: logging.Logger = logging.getLogger(__name__)

# How many times a custom command may redirect to another before we give up.
# Deep chains are almost always a mistake; the guard keeps a bad import from
# spinning the router.
_MAX_REDIRECT_DEPTH = 3


class _MessageRouterMixin:
    _background_tasks: set[asyncio.Task]

    def _fire_and_forget(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    # ------------------------------------------------------------------
    # Message trigger handling
    # ------------------------------------------------------------------

    async def _handle_message_trigger(self, payload: twitchio.ChatMessage) -> bool:
        """Check enabled triggers for the channel and respond to first match.

        Returns True if a trigger fired (caller should stop further processing).
        Only responds to top-level messages — ignores replies.
        Always-on: do NOT add an _active_sessions guard (timer_manager is the only gated component).
        """
        if payload.reply is not None:
            return False

        channel_id = payload.broadcaster.id
        text = payload.text or ""

        try:
            triggers = await self.message_trigger_configs.list_enabled(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"[TRIGGER] Failed to load triggers for channel {channel_id}: {e}")
            return False

        for trigger in triggers:
            if not match_trigger(trigger, text):
                continue
            if not has_role(payload.chatter, trigger.min_role):
                continue

            trigger_key = f"trigger:{trigger.id}"
            if is_on_cooldown(channel_id, trigger_key, trigger, None):
                continue
            record_cooldown(channel_id, trigger_key)

            response = _substitute_variables(
                trigger.response,
                payload.chatter,
                payload.broadcaster.name or "",
                text,
                # usage_count is the pre-increment value; $(count) reports the
                # firing we are currently serving, matching Nightbot's behaviour.
                count=trigger.usage_count + 1,
            )
            try:
                await payload.broadcaster.send_message(
                    message=response,
                    sender=self.sender_for(channel_id),  # type: ignore[attr-defined]
                    reply_to_message_id=str(payload.id),
                )
                LOGGER.info(
                    f"[TRIGGER] '{trigger.trigger_name}' fired for "
                    f"{payload.chatter.name} in channel {channel_id}"
                )
                self._fire_and_forget(
                    self.message_trigger_configs.increment_usage_count(trigger.id)  # type: ignore[attr-defined]
                )
            except Exception as e:
                LOGGER.warning(f"[TRIGGER] Failed to send trigger response: {e}")
            return True

        return False

    # ------------------------------------------------------------------
    # Custom command handling
    # ------------------------------------------------------------------

    async def _handle_custom_command(self, payload: twitchio.ChatMessage) -> bool:
        """Handle custom commands, following redirects between them.

        Returns True if fully handled (skip builtin pipeline), False if the
        message should continue to the builtin command pipeline.

        A ``custom_response`` beginning with ``!`` is a redirect. Redirects are
        resolved in a loop so one custom command can call another — the common
        shape of an imported Nightbot alias. Without the loop a redirect could
        only ever reach a builtin, because the builtin pipeline runs after this
        handler and never re-enters it.
        """
        visited: set[str] = set()
        for _ in range(_MAX_REDIRECT_DEPTH + 1):
            result = await self._dispatch_custom_command(payload, visited)
            if result is not None:
                return result
        LOGGER.warning(
            f"[CMD] Redirect chain exceeded {_MAX_REDIRECT_DEPTH} hops, dropping: {visited}"
        )
        return True

    async def _dispatch_custom_command(
        self, payload: twitchio.ChatMessage, visited: set[str]
    ) -> bool | None:
        """Run one step of custom command handling.

        Returns True when handled, False when the message belongs to the builtin
        pipeline, and None when a redirect rewrote ``payload.text`` and the
        caller should dispatch again.
        Always-on: usage_count incremented unconditionally; session analytics recorded separately.
        """
        text = payload.text
        if not text or not text.startswith("!"):
            return False

        parts = text[1:].split(maxsplit=1)
        if not parts or not parts[0]:
            return False

        cmd_name = parts[0].lower()
        query = parts[1] if len(parts) > 1 else ""

        if cmd_name in visited:
            LOGGER.warning(f"[CMD] Redirect loop on !{cmd_name}, dropping: {visited}")
            return True
        visited.add(cmd_name)

        channel_id = payload.broadcaster.id

        try:
            config = await self.command_configs.find_by_name_or_alias(channel_id, cmd_name)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(
                f"[CMD] DB error looking up command '{cmd_name}': {type(e).__name__}: {e}"
            )
            return False

        if not config or not config.enabled or config.command_type != "custom":
            return False

        if not config.custom_response:
            return False

        if not has_role(payload.chatter, config.min_role):
            return False

        try:
            channel = await self.channels.get_channel(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"[CMD] DB error fetching channel {channel_id}: {type(e).__name__}: {e}")
            channel = None

        if is_on_cooldown(channel_id, config.command_name, config, channel):
            return False

        record_cooldown(channel_id, config.command_name)

        self._fire_and_forget(
            self.command_configs.increment_usage_count(channel_id, config.command_name)  # type: ignore[attr-defined]
        )
        self._record_custom_command_analytics(channel_id, cmd_name)

        response = config.custom_response
        if response.startswith("!"):
            redirect = response[1:].replace("$(query)", query).strip()
            payload.text = f"!{redirect}"
            LOGGER.info(f"[CMD] !{cmd_name} -> !{redirect}")
            return None
        else:
            response = _substitute_variables(
                response,
                payload.chatter,
                payload.broadcaster.name or "",
                query,
                count=config.usage_count + 1,
            )
            try:
                await payload.broadcaster.send_message(
                    message=response,
                    sender=self.sender_for(channel_id),  # type: ignore[attr-defined]
                    reply_to_message_id=str(payload.id),
                )
                LOGGER.info(f"[CMD] !{cmd_name} -> text response")
            except Exception as e:
                LOGGER.warning(f"[CMD] Failed to send response for !{cmd_name}: {e}")
            return True

    def _record_custom_command_analytics(self, channel_id: str, cmd_name: str) -> None:
        """Record custom command usage to session analytics if a stream is live."""
        session_id = self.sessions.session_id(channel_id)  # type: ignore[attr-defined]
        if session_id:
            self._fire_and_forget(
                self.analytics.record_command_usage(  # type: ignore[attr-defined]
                    session_id=session_id,
                    channel_id=channel_id,
                    command_name=f"!{cmd_name}",
                )
            )
