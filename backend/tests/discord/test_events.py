"""Tests for cogs.events (EventsCog and helper functions)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from cogs.events import (
    EventsCog,
    _find_deleter,
    _load_log_channels,
    _save_log_channels,
    _top_role_color,
)
from core import EmbedFactory

# ── Fixtures & helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def cog():
    # Real EmbedFactory with empty config so .build(title=…) returns a real
    # discord.Embed (tests assert on embed.title), without touching disk.
    with (
        patch("cogs.events._load_log_channels", return_value={}),
        patch("cogs.events.EmbedFactory.default", return_value=EmbedFactory({})),
    ):
        bot = MagicMock(spec=commands.Bot)
        c = EventsCog(bot)
    c._send_log = AsyncMock()
    return c


def _make_guild(guild_id: int = 1) -> MagicMock:
    g = MagicMock(spec=discord.Guild)
    g.id = guild_id
    g.name = "TestGuild"
    return g


def _make_member(guild=None, *, bot: bool = False, member_id: int = 42) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.bot = bot
    m.id = member_id
    m.guild = guild or _make_guild()
    m.display_name = "TestUser"
    m.display_avatar = MagicMock()
    m.display_avatar.url = "https://cdn.discord.com/avatar.png"
    m.mention = f"<@{member_id}>"
    m._user = MagicMock()
    m._user.avatar_decoration = None
    m._user.primary_guild = None
    m.roles = []
    m.joined_at = datetime.now(UTC)
    return m


def _make_message(
    guild=None,
    *,
    is_bot: bool = False,
    content: str = "hello",
    msg_id: int = 999,
) -> MagicMock:
    guild = guild or _make_guild()
    author = _make_member(guild=guild, bot=is_bot)
    msg = MagicMock(spec=discord.Message)
    msg.id = msg_id
    msg.bot = is_bot
    msg.author = author
    msg.guild = guild
    msg.content = content
    msg.attachments = []
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.mention = "#general"
    msg.created_at = datetime.now(UTC)
    msg.jump_url = f"https://discord.com/channels/1/2/{msg_id}"
    return msg


# ── _top_role_color ────────────────────────────────────────────────────────────


def _make_role(color_value: int) -> MagicMock:
    r = MagicMock(spec=discord.Role)
    r.color = discord.Color(color_value)
    r.name = "role"
    return r


class TestTopRoleColor:
    def test_returns_top_colored_role(self):
        member = _make_member()
        r1 = _make_role(0xFF0000)  # red — lower position
        r2 = _make_role(0x00FF00)  # green — highest position (last in reversed list)
        member.roles = [r1, r2]
        assert _top_role_color(member) == (0, 255, 0)

    def test_skips_zero_color_roles(self):
        member = _make_member()
        r_no_color = _make_role(0)
        r_colored = _make_role(0xFF0000)
        member.roles = [r_colored, r_no_color]  # r_no_color is "top"
        assert _top_role_color(member) == (255, 0, 0)

    def test_all_uncolored_returns_none(self):
        member = _make_member()
        member.roles = [_make_role(0), _make_role(0)]
        assert _top_role_color(member) is None

    def test_no_roles_returns_none(self):
        member = _make_member()
        member.roles = []
        assert _top_role_color(member) is None


# ── _load_log_channels / _save_log_channels ────────────────────────────────────


class TestLogChannelPersistence:
    def test_load_missing_file_returns_empty(self, tmp_path):
        with patch("cogs.events._LOG_CHANNELS_FILE", tmp_path / "nonexistent.json"):
            assert _load_log_channels() == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        fp = tmp_path / "lc.json"
        with patch("cogs.events._LOG_CHANNELS_FILE", fp):
            _save_log_channels({1: 100, 2: 200})
            result = _load_log_channels()
        assert result == {1: 100, 2: 200}

    def test_corrupt_json_returns_empty(self, tmp_path):
        fp = tmp_path / "lc.json"
        fp.write_text("not json {{", encoding="utf-8")
        with patch("cogs.events._LOG_CHANNELS_FILE", fp):
            assert _load_log_channels() == {}


# ── _find_deleter ──────────────────────────────────────────────────────────────


def _make_audit_entry(author_id: int, channel_id: int, user=None, age_seconds: float = 0):
    entry = MagicMock()
    entry.target = MagicMock()
    entry.target.id = author_id
    entry.extra = MagicMock()
    entry.extra.channel = MagicMock()
    entry.extra.channel.id = channel_id
    entry.created_at = datetime.now(UTC)
    entry.user = user or MagicMock()
    return entry


class TestFindDeleter:
    pytestmark = pytest.mark.asyncio

    async def test_returns_user_from_matching_audit_entry(self):
        deleter = MagicMock(spec=discord.Member)
        entry = _make_audit_entry(author_id=42, channel_id=10, user=deleter)
        guild = _make_guild()

        async def mock_logs(**kwargs):
            yield entry

        guild.audit_logs = mock_logs

        with patch("cogs.events.asyncio.sleep", new_callable=AsyncMock):
            result = await _find_deleter(guild, channel_id=10, author_id=42)

        assert result is deleter

    async def test_returns_none_when_no_matching_entry(self):
        entry = _make_audit_entry(author_id=99, channel_id=10)  # different author
        guild = _make_guild()

        async def mock_logs(**kwargs):
            yield entry

        guild.audit_logs = mock_logs

        with patch("cogs.events.asyncio.sleep", new_callable=AsyncMock):
            result = await _find_deleter(guild, channel_id=10, author_id=42)

        assert result is None

    async def test_returns_none_on_forbidden(self):
        guild = _make_guild()

        async def mock_logs(**kwargs):
            raise discord.Forbidden(MagicMock(), "no perms")
            yield  # make it an async generator

        guild.audit_logs = mock_logs

        with patch("cogs.events.asyncio.sleep", new_callable=AsyncMock):
            result = await _find_deleter(guild, channel_id=10, author_id=42)

        assert result is None


# ── EventsCog.get_log_channel ─────────────────────────────────────────────────


class TestGetLogChannel:
    def test_returns_channel_when_set(self, cog):
        guild = _make_guild(guild_id=1)
        channel = MagicMock(spec=discord.TextChannel)
        guild.get_channel = MagicMock(return_value=channel)
        cog.log_channels[1] = 100
        assert cog.get_log_channel(guild) is channel

    def test_returns_none_when_not_set(self, cog):
        guild = _make_guild(guild_id=1)
        assert cog.get_log_channel(guild) is None

    def test_returns_none_when_channel_is_wrong_type(self, cog):
        guild = _make_guild(guild_id=1)
        guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.VoiceChannel))
        cog.log_channels[1] = 100
        assert cog.get_log_channel(guild) is None


# ── on_message ────────────────────────────────────────────────────────────────


class TestOnMessage:
    pytestmark = pytest.mark.asyncio

    async def test_caches_non_bot_guild_message(self, cog):
        msg = _make_message()
        await cog.on_message(msg)
        assert cog._msg_cache[msg.id] is msg

    async def test_skips_bot_messages(self, cog):
        msg = _make_message(is_bot=True)
        await cog.on_message(msg)
        assert msg.id not in cog._msg_cache

    async def test_skips_dm_messages(self, cog):
        msg = _make_message()
        msg.guild = None
        await cog.on_message(msg)
        assert msg.id not in cog._msg_cache


# ── on_message_delete ─────────────────────────────────────────────────────────


class TestOnMessageDelete:
    def test_skip_delete_log_adds_id(self, cog):
        cog.skip_delete_log(999)
        assert 999 in cog._log_skip_ids

    @pytest.mark.asyncio
    async def test_skips_registered_id_and_clears_it(self, cog):
        msg = _make_message(msg_id=123)
        cog.skip_delete_log(123)
        await cog.on_message_delete(msg)
        cog._send_log.assert_not_called()
        assert 123 not in cog._log_skip_ids

    @pytest.mark.asyncio
    async def test_skips_bot_message(self, cog):
        msg = _make_message(is_bot=True)
        await cog.on_message_delete(msg)
        cog._send_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_log_channel(self, cog):
        msg = _make_message()
        cog.log_channels.clear()
        await cog.on_message_delete(msg)
        cog._send_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_embed_without_image_when_content_unavailable(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        msg = _make_message(guild=guild, content="")
        msg.attachments = []

        with (
            patch("cogs.events._find_deleter", new_callable=AsyncMock, return_value=None),
        ):
            await cog.on_message_delete(msg)

        cog._send_log.assert_called_once()
        _, kwargs = cog._send_log.call_args
        assert kwargs.get("image_bytes") is None or len(cog._send_log.call_args.args) == 2

    @pytest.mark.asyncio
    async def test_renders_image_for_cached_message_with_content(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        msg = _make_message(guild=guild, content="Hello world")
        cog._msg_cache[msg.id] = msg

        with (
            patch("cogs.events._find_deleter", new_callable=AsyncMock, return_value=None),
            patch(
                "cogs.events.render_message_image",
                new_callable=AsyncMock,
                return_value=b"fakepng",
            ),
        ):
            await cog.on_message_delete(msg)

        cog._send_log.assert_called_once()
        call_args = cog._send_log.call_args
        assert call_args.args[2] == b"fakepng"


# ── on_message_edit ───────────────────────────────────────────────────────────


class TestOnMessageEdit:
    pytestmark = pytest.mark.asyncio

    async def test_skips_when_content_unchanged(self, cog):
        msg = _make_message(content="same")
        await cog.on_message_edit(msg, msg)
        cog._send_log.assert_not_called()

    async def test_updates_cache_and_sends_log(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        before = _make_message(guild=guild, content="old", msg_id=77)
        after = _make_message(guild=guild, content="new", msg_id=77)
        after.guild = guild
        cog._msg_cache[77] = before  # pre-cache old version

        await cog.on_message_edit(before, after)

        assert cog._msg_cache.get(77) is after
        cog._send_log.assert_called_once()


# ── on_member_update ──────────────────────────────────────────────────────────


class TestOnMemberUpdate:
    pytestmark = pytest.mark.asyncio

    async def test_skips_when_no_changes(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        before = _make_member(guild=guild)
        after = _make_member(guild=guild)
        before.nick = after.nick = "same"
        before.roles = after.roles = []

        await cog.on_member_update(before, after)
        cog._send_log.assert_not_called()

    async def test_logs_nick_change(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        before = _make_member(guild=guild)
        after = _make_member(guild=guild)
        before.nick = "OldNick"
        after.nick = "NewNick"
        before.roles = after.roles = []

        await cog.on_member_update(before, after)
        cog._send_log.assert_called_once()

    async def test_logs_role_change(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        before = _make_member(guild=guild)
        after = _make_member(guild=guild)
        before.nick = after.nick = None
        role = _make_role(0xFF0000)
        role.mention = "<@&1>"
        before.roles = []
        after.roles = [role]

        await cog.on_member_update(before, after)
        cog._send_log.assert_called_once()


# ── on_member_remove ─────────────────────────────────────────────────────────


class TestOnMemberRemove:
    pytestmark = pytest.mark.asyncio

    async def test_logs_voluntary_leave(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        member = _make_member(guild=guild)

        async def empty_logs(**kwargs):
            return
            yield

        guild.audit_logs = empty_logs

        with patch("cogs.events.asyncio.sleep", new_callable=AsyncMock):
            await cog.on_member_remove(member)

        cog._send_log.assert_called_once()
        embed_arg = cog._send_log.call_args.args[1]
        assert embed_arg.title == "成員離開"

    async def test_logs_kick_with_kicker(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        member = _make_member(guild=guild)
        kicker = MagicMock(spec=discord.Member)
        kicker.mention = "<@99>"

        kick_entry = MagicMock()
        kick_entry.target = MagicMock()
        kick_entry.target.id = member.id
        kick_entry.created_at = datetime.now(UTC)
        kick_entry.user = kicker

        async def mock_logs(**kwargs):
            yield kick_entry

        guild.audit_logs = mock_logs

        with patch("cogs.events.asyncio.sleep", new_callable=AsyncMock):
            await cog.on_member_remove(member)

        cog._send_log.assert_called_once()
        embed_arg = cog._send_log.call_args.args[1]
        assert embed_arg.title == "成員被踢出"


# ── on_bulk_message_delete ────────────────────────────────────────────────────


class TestOnBulkMessageDelete:
    pytestmark = pytest.mark.asyncio

    async def test_clears_cached_messages_and_sends_log(self, cog):
        guild = _make_guild(guild_id=1)
        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 50
        cog.log_channels[1] = 50
        guild.get_channel = MagicMock(return_value=log_ch)

        msgs = [_make_message(guild=guild, msg_id=i) for i in range(3)]
        for m in msgs:
            cog._msg_cache[m.id] = m

        await cog.on_bulk_message_delete(msgs)

        for m in msgs:
            assert m.id not in cog._msg_cache
        cog._send_log.assert_called_once()

    async def test_skips_when_no_log_channel(self, cog):
        msgs = [_make_message()]
        cog.log_channels.clear()
        await cog.on_bulk_message_delete(msgs)
        cog._send_log.assert_not_called()
