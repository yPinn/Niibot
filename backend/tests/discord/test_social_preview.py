"""Unit tests for discord.cogs.social_preview.

Covers:
  - constants: URL regex patterns (match / no-match)
  - _embeds: per-platform embed builders
  - cog: _OGParser/_parse_og, _DismissView permission logic, platform handlers (mocked HTTP)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview.cog import (
    SocialPreviewCog,
    _DismissView,
    _parse_og,
)
from discord.ext import commands

from core import EmbedFactory


@pytest.fixture
def embed_factory() -> EmbedFactory:
    """Minimal EmbedFactory with no chrome (empty config) for unit tests."""
    return EmbedFactory({})


# ===========================================================================
# constants — URL regex patterns
# ===========================================================================


class TestInstagramRE:
    RE = constants.INSTAGRAM_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/p/Abc123/",
            "https://instagram.com/p/Abc123",
            "https://www.instagram.com/reel/XYZ789/",
            "https://www.instagram.com/tv/QQQ111/",
            "http://instagram.com/p/lower-case/",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/",
            "https://www.instagram.com/someuser/",
            "https://twitter.com/p/Abc123/",
            "https://notinstagram.com/p/Abc123/",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    def test_captures_shortcode(self) -> None:
        m = self.RE.search("https://www.instagram.com/p/Abc123XYZ/")
        assert m is not None
        assert m.group(1) == "p"
        assert m.group(2) == "Abc123XYZ"

    def test_captures_reel_shortcode(self) -> None:
        m = self.RE.search("https://www.instagram.com/reel/DWpu7y3Dz2k/")
        assert m is not None
        assert m.group(1) == "reel"
        assert m.group(2) == "DWpu7y3Dz2k"


class TestThreadsRE:
    RE = constants.THREADS_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.threads.net/@user/post/AbcDef123",
            "https://threads.net/@user.name/post/XYZ",
            "https://www.threads.com/@user/post/AbcDef123",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.threads.net/@user",
            "https://threads.net/",
            "https://notthreads.net/@user/post/Abc",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None


class TestBilibiliRE:
    RE = constants.BILIBILI_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://bilibili.com/video/BVabcDEF123",
            "https://b23.tv/AbCdEf",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/",
            "https://www.bilibili.com/video/",
            "https://youtube.com/watch?v=BV1xx411c7mD",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    def test_captures_bvid_from_full_url(self) -> None:
        m = self.RE.search("https://www.bilibili.com/video/BV1xx411c7mD")
        assert m is not None
        assert m.group(1) == "BV1xx411c7mD"

    def test_short_url_group1_is_none(self) -> None:
        m = self.RE.search("https://b23.tv/AbCdEf")
        assert m is not None
        assert m.group(1) is None


class TestTiktokRE:
    RE = constants.TIKTOK_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.tiktok.com/@username/video/1234567890123456789",
            "https://vm.tiktok.com/AbCdEf1/",
            "https://vt.tiktok.com/ZSAbCdEf/",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.tiktok.com/",
            "https://www.tiktok.com/@username",
            "https://notiktok.com/@user/video/123",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None


# ===========================================================================
# _embeds — embed builders
# ===========================================================================


class TestBuildSocialEmbed:
    def test_returns_discord_embed(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_social_embed(
            embed_factory, platform="Test", color=0xFF0000, url="https://example.com"
        )
        assert isinstance(embed, discord.Embed)

    def test_footer_is_platform_name(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_social_embed(
            embed_factory, platform="Instagram", color=0xFF0000, url="https://example.com"
        )
        assert embed.footer.text == "Instagram"

    def test_color_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_social_embed(
            embed_factory, platform="X", color=0x123456, url="https://example.com"
        )
        assert embed.color.value == 0x123456

    def test_url_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_social_embed(
            embed_factory, platform="X", color=0x000000, url="https://example.com/post"
        )
        assert embed.url == "https://example.com/post"

    def test_title_truncated_to_256(self, embed_factory: EmbedFactory) -> None:
        long_title = "A" * 300
        embed = embeds_mod.build_social_embed(
            embed_factory, platform="X", color=0x000000, url="https://example.com", title=long_title
        )
        assert len(embed.title) == 256
        assert embed.title.endswith("…")

    def test_description_truncated(self, embed_factory: EmbedFactory) -> None:
        long_desc = "B" * 400
        embed = embeds_mod.build_social_embed(
            embed_factory,
            platform="X",
            color=0x000000,
            url="https://example.com",
            description=long_desc,
        )
        assert len(embed.description) == constants.DESCRIPTION_LIMIT
        assert embed.description.endswith("…")

    def test_description_short_not_truncated(self, embed_factory: EmbedFactory) -> None:
        short = "Hello world"
        embed = embeds_mod.build_social_embed(
            embed_factory,
            platform="X",
            color=0x000000,
            url="https://example.com",
            description=short,
        )
        assert embed.description == short

    def test_image_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_social_embed(
            embed_factory,
            platform="X",
            color=0x000000,
            url="https://example.com",
            image_url="https://example.com/img.jpg",
        )
        assert embed.image.url == "https://example.com/img.jpg"

    def test_no_author_when_none(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_social_embed(
            embed_factory, platform="X", color=0x000000, url="https://example.com"
        )
        assert embed.author.name is None

    def test_footer_inherits_cfg_icon(self) -> None:
        factory = EmbedFactory({"footer": {"icon_url": "https://example.com/icon.png"}})
        embed = embeds_mod.build_social_embed(
            factory, platform="Instagram", color=0xFF0000, url="https://example.com"
        )
        assert embed.footer.text == "Instagram"
        assert embed.footer.icon_url == "https://example.com/icon.png"


class TestBuildInstagramEmbed:
    def _og(self, title: str = "User on Instagram", description: str = "Caption") -> dict:
        return {"title": title, "description": description, "image": "https://img.com/p.jpg"}

    def test_author_is_instagram_platform(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(
            embed_factory, self._og(), "https://instagram.com/p/X/"
        )
        assert embed.author.name == "Instagram"

    def test_title_is_username(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(
            embed_factory, self._og(), "https://instagram.com/p/X/"
        )
        assert embed.title == "User"

    def test_at_handle_format_used_as_title(self, embed_factory: EmbedFactory) -> None:
        # InstaFix newer format: twitter:title is just "@handle"
        embed = embeds_mod.build_instagram_embed(
            embed_factory, {"title": "@dawei2707", "description": "caption"}, "https://example.com"
        )
        assert embed.title == "@dawei2707"

    def test_no_title_gives_none(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(
            embed_factory, {"description": "Hi"}, "https://example.com"
        )
        assert embed.title is None

    def test_no_thumbnail_by_default(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(embed_factory, self._og(), "https://example.com")
        assert embed.thumbnail.url is None

    def test_description_used(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(embed_factory, self._og(), "https://example.com")
        assert embed.description == "Caption"

    def test_image_url_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(embed_factory, self._og(), "https://example.com")
        assert embed.image.url == "https://img.com/p.jpg"

    def test_footer_uses_niibot_default(self, embed_factory: EmbedFactory) -> None:
        # Instagram uses use_platform_footer=False → footer from config (empty in test EmbedFactory)
        embed = embeds_mod.build_instagram_embed(embed_factory, self._og(), "https://example.com")
        assert embed.footer.text is None

    def test_empty_og_does_not_raise(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(embed_factory, {}, "https://example.com")
        assert isinstance(embed, discord.Embed)


class TestBuildThreadsEmbed:
    def _og(self) -> dict:
        return {
            "title": "ThreadsUser on Threads",
            "description": "Some post",
            "image": "https://img.com/t.jpg",
        }

    def test_strips_on_threads_from_title(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(
            embed_factory, self._og(), "https://threads.net/@u/post/X"
        )
        assert embed.author.name == "ThreadsUser"

    def test_footer_is_threads(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(
            embed_factory, self._og(), "https://threads.net/@u/post/X"
        )
        assert embed.footer.text == "Threads"

    def test_description_used(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(
            embed_factory, self._og(), "https://threads.net/@u/post/X"
        )
        assert embed.description == "Some post"


class TestBuildBilibiliEmbed:
    def _data(self) -> dict:
        return {
            "title": "My Video",
            "desc": "A description",
            "pic": "https://img.com/v.jpg",
            "owner": {"name": "Creator", "face": "https://img.com/avatar.jpg"},
            "stat": {"view": 1000, "like": 500, "coin": 100, "favorite": 200},
        }

    def test_title_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.title == "My Video"

    def test_author_name_from_owner(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.author.name == "Creator"

    def test_metrics_field_added(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert len(embed.fields) == 1
        field_value = embed.fields[0].value
        assert "▶" in field_value
        assert "👍" in field_value

    def test_no_metrics_field_when_stat_empty(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["stat"] = {}
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert len(embed.fields) == 0

    def test_desc_equals_title_suppresses_description(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["desc"] = "My Video"  # same as title
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert embed.description is None

    def test_footer_is_bilibili(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.footer.text == "Bilibili"

    def test_image_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.image.url == "https://img.com/v.jpg"


class TestBuildTiktokEmbed:
    def _oembed(self) -> dict:
        return {
            "title": "Funny video",
            "author_name": "@creator",
            "author_url": "https://tiktok.com/@creator",
            "thumbnail_url": "https://img.com/thumb.jpg",
        }

    def test_title_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_tiktok_embed(
            embed_factory, self._oembed(), "https://www.tiktok.com/@creator/video/123"
        )
        assert embed.title == "Funny video"

    def test_author_name_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_tiktok_embed(
            embed_factory, self._oembed(), "https://www.tiktok.com/@creator/video/123"
        )
        assert embed.author.name == "@creator"

    def test_thumbnail_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_tiktok_embed(
            embed_factory, self._oembed(), "https://www.tiktok.com/@creator/video/123"
        )
        assert embed.image.url == "https://img.com/thumb.jpg"

    def test_footer_is_tiktok(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_tiktok_embed(
            embed_factory, self._oembed(), "https://www.tiktok.com/@creator/video/123"
        )
        assert embed.footer.text == "TikTok"


# ===========================================================================
# cog — _OGParser / _parse_og
# ===========================================================================


class TestOGParser:
    def test_parses_og_title(self) -> None:
        html = '<meta property="og:title" content="Hello World">'
        og = _parse_og(html)
        assert og["title"] == "Hello World"

    def test_parses_og_description(self) -> None:
        html = '<meta property="og:description" content="Some desc">'
        og = _parse_og(html)
        assert og["description"] == "Some desc"

    def test_parses_og_image(self) -> None:
        html = '<meta property="og:image" content="https://img.com/i.jpg">'
        og = _parse_og(html)
        assert og["image"] == "https://img.com/i.jpg"

    def test_first_occurrence_wins(self) -> None:
        html = (
            '<meta property="og:title" content="First"><meta property="og:title" content="Second">'
        )
        og = _parse_og(html)
        assert og["title"] == "First"

    def test_non_og_meta_ignored(self) -> None:
        html = '<meta name="description" content="Not OG">'
        og = _parse_og(html)
        assert "description" not in og

    def test_empty_content_ignored(self) -> None:
        html = '<meta property="og:title" content="">'
        og = _parse_og(html)
        assert "title" not in og

    def test_returns_empty_for_no_og_tags(self) -> None:
        assert _parse_og("<html><body>Nothing here</body></html>") == {}

    def test_truncates_html_to_20k_chars(self) -> None:
        # Build a doc where og:title only appears after 25k chars (past the 20k limit)
        prefix = "<!-- " + "x" * 20_000 + " -->"
        og_part = '<meta property="og:title" content="Late Title">'
        html = prefix + og_part
        og = _parse_og(html)
        assert "title" not in og


# ===========================================================================
# cog — _DismissView permission logic
# ===========================================================================


class TestDismissView:
    def _make_view(self, author_id: int = 111) -> _DismissView:
        return _DismissView(user_id=author_id)

    def _make_interaction(
        self,
        user_id: int,
        *,
        has_manage_messages: bool = False,
        in_text_channel: bool = True,
    ) -> MagicMock:
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = user_id

        if in_text_channel:
            channel = MagicMock(spec=discord.TextChannel)
            perms = MagicMock(spec=discord.Permissions)
            perms.manage_messages = has_manage_messages
            channel.permissions_for.return_value = perms
            interaction.channel = channel
        else:
            interaction.channel = MagicMock()

        interaction.message = AsyncMock()
        interaction.response = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_author_passes_interaction_check(self) -> None:
        view = self._make_view(author_id=42)
        interaction = self._make_interaction(user_id=42)
        assert await view.interaction_check(interaction) is True

    @pytest.mark.asyncio
    async def test_moderator_passes_interaction_check(self) -> None:
        view = self._make_view(author_id=42)
        interaction = self._make_interaction(user_id=99, has_manage_messages=True)
        assert await view.interaction_check(interaction) is True

    @pytest.mark.asyncio
    async def test_non_author_without_perms_fails_interaction_check(self) -> None:
        view = self._make_view(author_id=42)
        interaction = self._make_interaction(user_id=99, has_manage_messages=False)
        result = await view.interaction_check(interaction)
        assert result is False
        interaction.response.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dismiss_deletes_message(self) -> None:
        view = self._make_view(author_id=42)
        interaction = self._make_interaction(user_id=42)
        # _ItemCallback binds view+button; call signature is just (interaction,)
        await view.dismiss.callback(interaction)
        interaction.message.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_timeout_removes_view(self) -> None:
        view = self._make_view()
        message = AsyncMock()
        view.message = message
        await view.on_timeout()
        message.edit.assert_awaited_once_with(view=None)

    @pytest.mark.asyncio
    async def test_on_timeout_handles_not_found(self) -> None:
        view = self._make_view()
        message = AsyncMock()
        message.edit.side_effect = discord.NotFound(MagicMock(), "gone")
        view.message = message
        await view.on_timeout()  # Should not raise

    @pytest.mark.asyncio
    async def test_on_timeout_no_message_is_noop(self) -> None:
        view = self._make_view()
        # view.message is None by default
        await view.on_timeout()  # Should not raise


# ===========================================================================
# cog — SocialPreviewCog platform handlers (mocked HTTP)
# ===========================================================================


def _make_message(content: str, author_id: int = 1) -> AsyncMock:
    msg = AsyncMock(spec=discord.Message)
    msg.content = content
    msg.author = MagicMock()
    msg.author.bot = False
    msg.author.id = author_id
    msg.guild = MagicMock()
    msg.channel = AsyncMock()
    msg.channel.send = AsyncMock(return_value=AsyncMock(spec=discord.Message))
    msg.delete = AsyncMock()
    return msg


@pytest.fixture
def cog(embed_factory: EmbedFactory) -> SocialPreviewCog:
    bot = MagicMock(spec=commands.Bot)
    c = SocialPreviewCog.__new__(SocialPreviewCog)
    c.bot = bot
    c._embed = embed_factory
    c._http = AsyncMock()
    return c


class TestCogOnMessage:
    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        msg.author.bot = True
        await cog.on_message(msg)
        cog._http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_dm_messages(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        msg.guild = None
        await cog.on_message(msg)
        cog._http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_plain_message(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("hello world, no links here")
        await cog.on_message(msg)
        cog._http.get.assert_not_called()


class TestCogInstagram:
    def _make_og_resp(self, og_html: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.is_redirect = False
        resp.text = og_html
        return resp

    def _make_redirect_resp(self, location: str) -> MagicMock:
        resp = MagicMock()
        resp.is_redirect = True
        resp.headers = {"location": location}
        return resp

    def _default_side_effects(self, og_html: str, cdn_url: str) -> list:
        """post OG → image redirect."""
        return [
            self._make_og_resp(og_html),
            self._make_redirect_resp(cdn_url),
        ]

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        og_html = (
            '<meta property="og:title" content="User on Instagram">'
            '<meta property="og:description" content="Great photo">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        cog._http.get = AsyncMock(side_effect=self._default_side_effects(og_html, cdn_url))
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.footer.text is None  # Niibot config footer (empty in test EmbedFactory)

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        og_html = (
            '<meta property="og:title" content="User on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        cog._http.get = AsyncMock(side_effect=self._default_side_effects(og_html, cdn_url))
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_author_url_points_to_profile(self, cog: SocialPreviewCog) -> None:
        og_html = (
            '<meta property="og:title" content="minyeee_111 on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        cog._http.get = AsyncMock(side_effect=self._default_side_effects(og_html, cdn_url))
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.name == "Instagram"
        assert embed.author.url == "https://www.instagram.com/p/Abc123/"
        assert embed.title == "minyeee_111"

    @pytest.mark.asyncio
    async def test_no_send_on_fetch_failure(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("network error"))
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_send_when_og_empty(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_og_resp("<html></html>"))
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()


class TestCogTiktok:
    def _make_resp(self, data: dict) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=data)
        return resp

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        oembed = {
            "title": "Funny video",
            "author_name": "@creator",
            "author_url": "https://tiktok.com/@creator",
            "thumbnail_url": "https://img.com/thumb.jpg",
        }
        cog._http.get = AsyncMock(return_value=self._make_resp(oembed))
        msg = _make_message("https://www.tiktok.com/@creator/video/1234567890123456789")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.footer.text == "TikTok"
        assert embed.title == "Funny video"

    @pytest.mark.asyncio
    async def test_no_send_on_empty_oembed(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_resp({}))
        msg = _make_message("https://www.tiktok.com/@creator/video/1234567890123456789")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_send_on_http_error(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message("https://www.tiktok.com/@creator/video/1234567890123456789")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()


class TestCogBilibili:
    def _api_response(self) -> dict:
        return {
            "code": 0,
            "data": {
                "title": "My BV Video",
                "desc": "Some description",
                "pic": "https://img.com/v.jpg",
                "owner": {"name": "Uploader", "face": "https://img.com/a.jpg"},
                "stat": {"view": 5000, "like": 200, "coin": 50, "favorite": 100},
            },
        }

    def _make_resp(self, data: dict) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=data)
        return resp

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_resp(self._api_response()))
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.footer.text == "Bilibili"
        assert embed.title == "My BV Video"

    @pytest.mark.asyncio
    async def test_no_send_on_api_error_code(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_resp({"code": -404, "data": None}))
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_resp(self._api_response()))
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_send_on_http_error(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()


class TestCogThreads:
    def _make_resp(self, og_html: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.is_redirect = False
        resp.text = og_html
        return resp

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        html = (
            '<meta property="og:title" content="ThreadsUser on Threads">'
            '<meta property="og:description" content="Great post">'
        )
        cog._http.get = AsyncMock(return_value=self._make_resp(html))
        msg = _make_message("https://www.threads.net/@threaduser/post/AbcDef123")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.footer.text == "Threads"
        assert embed.author.name == "ThreadsUser"

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        html = '<meta property="og:title" content="User on Threads">'
        cog._http.get = AsyncMock(return_value=self._make_resp(html))
        msg = _make_message("https://www.threads.net/@threaduser/post/AbcDef123")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_send_on_fetch_failure(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message("https://www.threads.net/@threaduser/post/AbcDef123")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()
