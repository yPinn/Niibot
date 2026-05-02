"""Message routing mixin — handles message triggers and custom commands.

Extracted from Bot to keep bot.py under 300 lines.
Depends on attributes defined in Bot.__init__:
    self.bot_id, self.owner_id
    self.command_configs, self.redemption_configs
    self.message_trigger_configs, self.channels
"""

from __future__ import annotations

import asyncio
import logging

import twitchio

from core.guards import has_role, is_on_cooldown, record_cooldown
from utils.substitution import substitute_variables as _substitute_variables
from utils.trigger_matching import match_trigger

LOGGER: logging.Logger = logging.getLogger(__name__)


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
            )
            try:
                await payload.broadcaster.send_message(
                    message=response,
                    sender=self.bot_id,  # type: ignore[attr-defined]
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
        """Handle custom commands: direct text response or redirect to builtin command.

        Returns True if fully handled (text response sent, skip builtin pipeline),
        False if message should continue to builtin command pipeline.
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
            return False
        else:
            response = _substitute_variables(
                response, payload.chatter, payload.broadcaster.name or "", query
            )
            try:
                await payload.broadcaster.send_message(
                    message=response,
                    sender=self.bot_id,  # type: ignore[attr-defined]
                    reply_to_message_id=str(payload.id),
                )
                LOGGER.info(f"[CMD] !{cmd_name} -> text response")
            except Exception as e:
                LOGGER.warning(f"[CMD] Failed to send response for !{cmd_name}: {e}")
            return True

    def _record_custom_command_analytics(self, channel_id: str, cmd_name: str) -> None:
        """Record custom command usage to session analytics if a stream is live."""
        session_id = self._active_sessions.get(channel_id)  # type: ignore[attr-defined]
        if session_id:
            self._fire_and_forget(
                self.analytics.record_command_usage(  # type: ignore[attr-defined]
                    session_id=session_id,
                    channel_id=channel_id,
                    command_name=f"!{cmd_name}",
                )
            )
