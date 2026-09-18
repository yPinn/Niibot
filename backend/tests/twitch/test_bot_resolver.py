"""Tests for BotAccountResolver.

Focus areas:
- Default resolution: no row, or a NULL active_bot_user_id, means the system
  default speaks — this is every channel until a switch actually ships.
- `relevant_bot_ids()` is the load-bearing set for token loading: it must
  include desired (not just active) accounts, so a switch's target token can
  be loaded ahead of the swap.
- `is_bot_identity()` is intentionally broader than "this channel's sender" —
  it must recognise ANY bot account, for cross-tenant shared-chat suppression.
- Hot-path reads (`context`/`sender_id`/`is_bot_identity`/`relevant_bot_ids`)
  never touch the DB — only `load_all`/`refresh` do.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.bot_resolver import BotAccountResolver, BotExecutionContext


def _pool_with_rows(rows: list[dict]) -> MagicMock:
    """A pool whose `.acquire().fetch(...)` returns `rows` as dict-like records."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    conn.fetchrow = AsyncMock(return_value=rows[0] if rows else None)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool


class TestDefaultResolution:
    def test_unknown_channel_resolves_to_system_default(self):
        resolver = BotAccountResolver(
            MagicMock(), system_bot_id="niibot", system_bot_login="niibot_login"
        )
        ctx = resolver.context("ch1")
        assert ctx == BotExecutionContext(
            channel_id="ch1",
            sender_id="niibot",
            sender_login="niibot_login",
            is_system_default=True,
            selection_version=0,
        )

    def test_sender_id_shortcut_matches_context(self):
        resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
        assert resolver.sender_id("ch1") == "niibot"

    def test_set_system_bot_login_updates_default_context(self):
        resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
        resolver.set_system_bot_login("niibot_login")
        assert resolver.context("ch1").sender_login == "niibot_login"


class TestIsBotIdentity:
    def test_system_default_is_a_bot_identity(self):
        resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
        assert resolver.is_bot_identity("niibot") is True

    def test_ordinary_viewer_is_not_a_bot_identity(self):
        resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
        assert resolver.is_bot_identity("viewer-1") is False

    def test_none_is_not_a_bot_identity(self):
        resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
        assert resolver.is_bot_identity(None) is False

    @pytest.mark.asyncio
    async def test_custom_active_bot_is_a_bot_identity_after_load(self):
        pool = _pool_with_rows(
            [
                {
                    "channel_id": "ch1",
                    "active_bot_user_id": "custom-1",
                    "desired_bot_user_id": None,
                    "selection_version": 3,
                    "active_login": "custombot",
                    "desired_login": None,
                }
            ]
        )
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        await resolver.load_all()

        assert resolver.is_bot_identity("custom-1") is True
        # A custom bot active in one channel must not affect resolution
        # elsewhere — a different channel with no row still gets the default.
        assert resolver.sender_id("ch2") == "niibot"

    @pytest.mark.asyncio
    async def test_cross_channel_bot_identity_recognised_for_shared_chat(self):
        """A bot active in channel A must be recognised as a bot identity
        while processing messages in unrelated channel B — this is what
        stops one tenant's bot from dispatching another tenant's bot's
        messages as commands during a shared-chat session."""
        pool = _pool_with_rows(
            [
                {
                    "channel_id": "ch_a",
                    "active_bot_user_id": "bot-a",
                    "desired_bot_user_id": None,
                    "selection_version": 1,
                    "active_login": "bota",
                    "desired_login": None,
                }
            ]
        )
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        await resolver.load_all()

        assert resolver.is_bot_identity("bot-a") is True


class TestRelevantBotIds:
    pytestmark = pytest.mark.asyncio

    async def test_includes_system_default_with_no_custom_accounts(self):
        resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
        assert resolver.relevant_bot_ids() == frozenset({"niibot"})

    async def test_includes_desired_even_before_switch_completes(self):
        """A switch's target token must be loadable ahead of the swap —
        relevant_bot_ids() therefore includes desired, not just active."""
        pool = _pool_with_rows(
            [
                {
                    "channel_id": "ch1",
                    "active_bot_user_id": None,
                    "desired_bot_user_id": "custom-2",
                    "selection_version": 1,
                    "active_login": None,
                    "desired_login": "custombot2",
                }
            ]
        )
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        await resolver.load_all()

        assert resolver.relevant_bot_ids() == frozenset({"niibot", "custom-2"})
        # Not yet active, so the channel still resolves to the system default.
        assert resolver.sender_id("ch1") == "niibot"

    async def test_includes_both_active_and_desired(self):
        pool = _pool_with_rows(
            [
                {
                    "channel_id": "ch1",
                    "active_bot_user_id": "custom-1",
                    "desired_bot_user_id": "custom-2",
                    "selection_version": 2,
                    "active_login": "custombot",
                    "desired_login": "custombot2",
                }
            ]
        )
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        await resolver.load_all()

        assert resolver.relevant_bot_ids() == frozenset({"niibot", "custom-1", "custom-2"})
        assert resolver.sender_id("ch1") == "custom-1"


class TestLoadAllAndRefresh:
    pytestmark = pytest.mark.asyncio

    async def test_load_all_ignores_rows_with_no_active_or_desired(self):
        """A row can exist with both columns NULL (e.g. after switching back
        to the default) — it must not appear as a custom sender."""
        pool = _pool_with_rows([])
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        await resolver.load_all()

        assert resolver.sender_id("ch1") == "niibot"
        assert resolver.relevant_bot_ids() == frozenset({"niibot"})

    async def test_refresh_updates_a_single_channel_without_reloading_others(self):
        pool = _pool_with_rows(
            [
                {
                    "active_bot_user_id": "custom-9",
                    "desired_bot_user_id": None,
                    "selection_version": 5,
                    "active_login": "custombot9",
                    "desired_login": None,
                }
            ]
        )
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        # Seed an unrelated channel directly, as load_all would have.
        resolver._contexts["ch_other"] = BotExecutionContext(
            channel_id="ch_other",
            sender_id="custom-other",
            sender_login="other",
            is_system_default=False,
            selection_version=1,
        )

        ctx = await resolver.refresh("ch1")

        assert ctx.sender_id == "custom-9"
        assert ctx.selection_version == 5
        assert resolver.sender_id("ch_other") == "custom-other"

    async def test_refresh_with_no_row_falls_back_to_default_and_forgets_cache(self):
        pool = _pool_with_rows([])
        resolver = BotAccountResolver(pool, system_bot_id="niibot")
        resolver._contexts["ch1"] = BotExecutionContext(
            channel_id="ch1",
            sender_id="custom-1",
            sender_login="custombot",
            is_system_default=False,
            selection_version=1,
        )

        ctx = await resolver.refresh("ch1")

        assert ctx.is_system_default is True
        assert resolver.sender_id("ch1") == "niibot"


def test_forget_drops_cached_context():
    resolver = BotAccountResolver(MagicMock(), system_bot_id="niibot")
    resolver._contexts["ch1"] = BotExecutionContext(
        channel_id="ch1",
        sender_id="custom-1",
        sender_login="custombot",
        is_system_default=False,
        selection_version=1,
    )
    resolver.forget("ch1")
    assert resolver.sender_id("ch1") == "niibot"
