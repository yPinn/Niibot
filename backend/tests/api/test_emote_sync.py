"""Tests for services.emote_sync — per-channel bot account resolution and
other-channel emote grouping.

Focus: resolve_bot_id/resolve_bot_ids must mirror BotAccountResolver's
semantics in backend/twitch/core/bot_resolver.py exactly (no row, or a NULL
active_bot_user_id, means "use the system default"), bot_tokens_for must not
re-fetch a token it already fetched for a different channel sharing the same
bot account, and other_channel_emote_ids/build_other_channel_groups must
surface emotes the bot unlocked on OTHER channels (subscription emotes are
usable platform-wide) without leaking the current channel's own emotes or
Twitch globals into that grouping.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.emote_sync import (
    EmoteFetch,
    bot_tokens_for,
    build_other_channel_groups,
    notify_config_change,
    other_channel_emote_ids,
    resolve_bot_id,
    resolve_bot_ids,
)


def _fetch(*, channel_id: str = "ch1", channel_raw=None, user_raw=None) -> EmoteFetch:
    return EmoteFetch(
        channel_id=channel_id,
        channel_raw=channel_raw or [],
        global_raw=[],
        user_raw=user_raw or [],
        accessible={e["id"] for e in (user_raw or [])},
        bot_id="bot-1",
        bot_token_available=bool(user_raw),
    )


def _pool_with(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


class TestNotifyConfigChange:
    pytestmark = pytest.mark.asyncio

    async def test_memory_clear_intent_is_explicit_in_payload(self):
        conn = AsyncMock()
        pool = _pool_with(conn)

        await notify_config_change(
            pool,
            "ch1",
            clear_assistant_memory=True,
        )

        _, payload = conn.execute.await_args.args
        assert json.loads(payload) == {
            "channel_id": "ch1",
            "table": "ai_settings",
            "clear_assistant_memory": True,
        }


class TestResolveBotId:
    pytestmark = pytest.mark.asyncio

    async def test_no_row_falls_back_to_system_default(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _pool_with(conn)

        result = await resolve_bot_id(pool, "ch1", system_bot_id="niibot")

        assert result == "niibot"

    async def test_null_active_falls_back_to_system_default(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {"active_bot_user_id": None}
        pool = _pool_with(conn)

        result = await resolve_bot_id(pool, "ch1", system_bot_id="niibot")

        assert result == "niibot"

    async def test_custom_active_bot_is_returned(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {"active_bot_user_id": "custom-1"}
        pool = _pool_with(conn)

        result = await resolve_bot_id(pool, "ch1", system_bot_id="niibot")

        assert result == "custom-1"


class TestResolveBotIds:
    pytestmark = pytest.mark.asyncio

    async def test_empty_input_short_circuits_without_a_query(self):
        conn = AsyncMock()
        pool = _pool_with(conn)

        result = await resolve_bot_ids(pool, [], system_bot_id="niibot")

        assert result == {}
        conn.fetch.assert_not_awaited()

    async def test_every_requested_channel_gets_an_entry(self):
        """Channels with no override row must still appear in the result,
        defaulted to the system bot — a missing dict entry would KeyError at
        every call site that does bot_ids[channel_id]."""
        conn = AsyncMock()
        conn.fetch.return_value = [{"channel_id": "ch2", "active_bot_user_id": "custom-2"}]
        pool = _pool_with(conn)

        result = await resolve_bot_ids(pool, ["ch1", "ch2", "ch3"], system_bot_id="niibot")

        assert result == {"ch1": "niibot", "ch2": "custom-2", "ch3": "niibot"}


class TestBotTokensFor:
    pytestmark = pytest.mark.asyncio

    async def test_one_token_fetch_per_distinct_bot_id(self):
        """Three channels sharing two bot accounts must only issue two
        get_token calls, not three — admin's aggregate endpoint iterates many
        channels and must not refetch the same account's token repeatedly."""
        get_token_calls: list[str] = []

        async def _fake_get_token(user_id: str, token_type: str = "broadcaster"):
            get_token_calls.append(user_id)
            return MagicMock(token=f"tok-{user_id}")

        fake_repo = MagicMock()
        fake_repo.get_token = AsyncMock(side_effect=_fake_get_token)

        with patch("services.emote_sync.ChannelRepository", return_value=fake_repo):
            result = await bot_tokens_for(MagicMock(), ["bot-a", "bot-b", "bot-a"])

        assert sorted(get_token_calls) == ["bot-a", "bot-b"]
        assert result == {"bot-a": "tok-bot-a", "bot-b": "tok-bot-b"}

    async def test_missing_token_maps_to_none(self):
        fake_repo = MagicMock()
        fake_repo.get_token = AsyncMock(return_value=None)

        with patch("services.emote_sync.ChannelRepository", return_value=fake_repo):
            result = await bot_tokens_for(MagicMock(), ["bot-a"])

        assert result == {"bot-a": None}


class TestOtherChannelEmoteIds:
    def test_excludes_current_channel_and_globals(self):
        fetch = _fetch(
            channel_id="ch1",
            user_raw=[
                {"id": "e1", "owner_id": "ch1", "emote_type": "subscriptions"},  # own channel
                {"id": "e2", "owner_id": "twitch", "emote_type": "globals"},  # global
                {"id": "e3", "owner_id": "ch2", "emote_type": "subscriptions"},  # other channel
            ],
        )

        groups = other_channel_emote_ids(fetch)

        assert list(groups.keys()) == ["ch2"]
        assert [e["id"] for e in groups["ch2"]] == ["e3"]

    def test_excludes_entries_already_covered_by_channel_raw(self):
        """An emote id already present in the current channel's own list must
        not double up as an 'other channel' entry even if user_raw also
        returned it (e.g. a bit-unlocked emote the channel itself owns)."""
        fetch = _fetch(
            channel_id="ch1",
            channel_raw=[{"id": "e1"}],
            user_raw=[{"id": "e1", "owner_id": "ch2", "emote_type": "subscriptions"}],
        )

        assert other_channel_emote_ids(fetch) == {}

    def test_groups_multiple_emotes_from_the_same_channel(self):
        fetch = _fetch(
            channel_id="ch1",
            user_raw=[
                {"id": "e1", "owner_id": "ch2", "emote_type": "subscriptions"},
                {"id": "e2", "owner_id": "ch2", "emote_type": "subscriptions"},
            ],
        )

        groups = other_channel_emote_ids(fetch)

        assert {e["id"] for e in groups["ch2"]} == {"e1", "e2"}

    def test_missing_owner_id_is_excluded(self):
        fetch = _fetch(channel_id="ch1", user_raw=[{"id": "e1", "emote_type": "subscriptions"}])

        assert other_channel_emote_ids(fetch) == {}


class TestBuildOtherChannelGroups:
    pytestmark = pytest.mark.asyncio

    async def test_no_bot_token_returns_empty_without_calling_twitch(self):
        fetch = _fetch(channel_id="ch1", user_raw=[])
        twitch = MagicMock()
        twitch.get_users_by_ids = AsyncMock()

        result = await build_other_channel_groups(twitch, fetch)

        assert result == []
        twitch.get_users_by_ids.assert_not_awaited()

    async def test_resolves_names_and_builds_emote_items(self):
        fetch = _fetch(
            channel_id="ch1",
            user_raw=[
                {
                    "id": "e1",
                    "name": "ChanTwoSub",
                    "url": "https://cdn/e1.png",
                    "owner_id": "ch2",
                    "emote_type": "subscriptions",
                }
            ],
        )
        twitch = MagicMock()
        twitch.get_users_by_ids = AsyncMock(
            return_value=[
                {
                    "id": "ch2",
                    "login": "chantwo",
                    "display_name": "ChanTwo",
                    "profile_image_url": "https://img/ch2.png",
                }
            ]
        )

        [group] = await build_other_channel_groups(twitch, fetch)

        assert group.channel_id == "ch2"
        assert group.channel_name == "chantwo"
        assert group.display_name == "ChanTwo"
        assert group.avatar == "https://img/ch2.png"
        assert group.emotes[0].name == "ChanTwoSub"
        assert group.emotes[0].available is True

    async def test_unresolvable_owner_is_dropped_not_fatal(self):
        """A channel whose user info can't be resolved must be skipped, not
        crash the whole request."""
        fetch = _fetch(
            channel_id="ch1",
            user_raw=[{"id": "e1", "owner_id": "ch2", "emote_type": "subscriptions"}],
        )
        twitch = MagicMock()
        twitch.get_users_by_ids = AsyncMock(return_value=[])

        result = await build_other_channel_groups(twitch, fetch)

        assert result == []
