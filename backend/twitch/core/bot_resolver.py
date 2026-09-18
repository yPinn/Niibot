"""Per-channel bot sender resolution.

A channel normally speaks through the process's system-default bot account.
Phase 3 lets a tenant authorize and select a different Twitch account instead
(see docs/architecture/bot-accounts-and-collaboration.md). This module owns
the READ side of that mapping — which account currently speaks for which
channel. The write side (validating and initiating a switch) lives in the API
process; this resolver only ever reads `channel_bot_settings`/`bot_accounts`
and reacts to a `bot_selection_changed` notification (wired in a later PR).

A channel with no row, or a NULL `active_bot_user_id`, uses the system
default — this is every channel until a switch actually ships, so lookups
must be synchronous and infallible: a chat send can never block on, or be
broken by, a DB round-trip here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BotExecutionContext:
    """Which account currently speaks for one channel."""

    channel_id: str
    sender_id: str
    sender_login: str
    is_system_default: bool
    selection_version: int


class BotAccountResolver:
    """In-memory ``channel_id -> BotExecutionContext`` cache.

    Takes the raw pool rather than going through ``ChannelRepository`` —
    ``channel_bot_settings``/``bot_accounts`` belong to the bot-account
    feature, not that repository's token/channel surface.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        system_bot_id: str,
        system_bot_login: str = "",
    ) -> None:
        self.pool = pool
        self._system_bot_id = system_bot_id
        self._system_bot_login = system_bot_login
        self._contexts: dict[str, BotExecutionContext] = {}
        # bot_user_id -> login, for every non-default account currently
        # active OR desired anywhere. Kept separate from `_contexts` (which
        # only ever reflects `active`) so a switch's *target* token can be
        # loaded ahead of the swap without a channel resolving to it early.
        self._custom_logins: dict[str, str] = {}

    def set_system_bot_login(self, login: str) -> None:
        """Learn the system bot's own login once ``load_tokens()`` resolves it."""
        self._system_bot_login = login

    def _default_context(self, channel_id: str) -> BotExecutionContext:
        return BotExecutionContext(
            channel_id=channel_id,
            sender_id=self._system_bot_id,
            sender_login=self._system_bot_login,
            is_system_default=True,
            selection_version=0,
        )

    # ------------------------------------------------------------------
    # Hot-path reads — synchronous, never await, never raise.
    # ------------------------------------------------------------------

    def context(self, channel_id: str) -> BotExecutionContext:
        return self._contexts.get(channel_id) or self._default_context(channel_id)

    def sender_id(self, channel_id: str) -> str:
        return self.context(channel_id).sender_id

    def is_bot_identity(self, user_id: str | None) -> bool:
        """True for the system default OR any account active/desired anywhere.

        Deliberately broader than "this channel's sender" — in a shared-chat
        session, one tenant's bot must not treat another tenant's bot as a
        regular chatter and dispatch its messages as commands.
        """
        if user_id is None:
            return False
        return user_id == self._system_bot_id or user_id in self._custom_logins

    def relevant_bot_ids(self) -> frozenset[str]:
        """System default, union every account currently active or desired.

        This is the load-bearing set for `load_tokens()`/hot-reload: a bot
        token is only ever loaded into the TwitchIO token store for an id in
        this set, so an unlinked or never-selected custom account can't
        silently enter global state.
        """
        return frozenset({self._system_bot_id, *self._custom_logins})

    # ------------------------------------------------------------------
    # DB-backed loads — only at startup and on explicit refresh.
    # ------------------------------------------------------------------

    _SELECT_ONE = """
        SELECT cbs.active_bot_user_id, cbs.desired_bot_user_id, cbs.selection_version,
               ab.login AS active_login, db.login AS desired_login
        FROM channel_bot_settings cbs
        LEFT JOIN bot_accounts ab ON ab.platform_user_id = cbs.active_bot_user_id
        LEFT JOIN bot_accounts db ON db.platform_user_id = cbs.desired_bot_user_id
        WHERE cbs.channel_id = $1
    """

    def _apply_row(self, channel_id: str, row: asyncpg.Record) -> BotExecutionContext:
        active_id = row["active_bot_user_id"]
        desired_id = row["desired_bot_user_id"]
        if desired_id:
            self._custom_logins.setdefault(desired_id, row["desired_login"] or "")
        if not active_id:
            self._contexts.pop(channel_id, None)
            return self._default_context(channel_id)
        self._custom_logins[active_id] = row["active_login"] or ""
        context = BotExecutionContext(
            channel_id=channel_id,
            sender_id=active_id,
            sender_login=row["active_login"] or "",
            is_system_default=False,
            selection_version=row["selection_version"],
        )
        self._contexts[channel_id] = context
        return context

    async def load_all(self) -> None:
        """Warm the cache for every channel with a non-default row. Startup only."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cbs.channel_id, cbs.active_bot_user_id, cbs.desired_bot_user_id,
                       cbs.selection_version,
                       ab.login AS active_login, db.login AS desired_login
                FROM channel_bot_settings cbs
                LEFT JOIN bot_accounts ab ON ab.platform_user_id = cbs.active_bot_user_id
                LEFT JOIN bot_accounts db ON db.platform_user_id = cbs.desired_bot_user_id
                WHERE cbs.active_bot_user_id IS NOT NULL OR cbs.desired_bot_user_id IS NOT NULL
                """
            )
        self._contexts = {}
        self._custom_logins = {}
        for row in rows:
            self._apply_row(row["channel_id"], row)
        LOGGER.info(
            "Bot account resolver warmed: %d channel(s) on a custom sender", len(self._contexts)
        )

    async def refresh(self, channel_id: str) -> BotExecutionContext:
        """Reload one channel's row from DB — for the future `bot_selection_changed` handler."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(self._SELECT_ONE, channel_id)
        if row is None:
            self._contexts.pop(channel_id, None)
            return self._default_context(channel_id)
        return self._apply_row(channel_id, row)

    def forget(self, channel_id: str) -> None:
        """Drop cached state for a channel that was disabled/removed."""
        self._contexts.pop(channel_id, None)
