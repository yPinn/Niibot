"""Tests for shared embed builder and OG parser utilities."""

from __future__ import annotations

import discord
import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview.cog import SocialPreviewCog, _parse_og

from core import EmbedFactory

from ._helpers import _make_message

# ===========================================================================
# _embeds — build_social_embed (shared template)
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
        long_desc = "B" * (constants.DESCRIPTION_LIMIT + 100)
        embed = embeds_mod.build_social_embed(
            embed_factory,
            platform="X",
            color=0x000000,
            url="https://example.com",
            description=long_desc,
        )
        assert len(embed.description) == constants.DESCRIPTION_LIMIT
        assert embed.description.endswith("…")

    def test_description_truncates_at_word_boundary(self, embed_factory: EmbedFactory) -> None:
        prefix = "A" * (constants.DESCRIPTION_LIMIT - 10)
        long_desc = prefix + " " + "B" * 200
        embed = embeds_mod.build_social_embed(
            embed_factory,
            platform="X",
            color=0x000000,
            url="https://example.com",
            description=long_desc,
        )
        assert embed.description is not None
        assert len(embed.description) <= constants.DESCRIPTION_LIMIT
        assert embed.description.endswith("…")
        assert "B" not in embed.description

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
        prefix = "<!-- " + "x" * 20_000 + " -->"
        og_part = '<meta property="og:title" content="Late Title">'
        html = prefix + og_part
        og = _parse_og(html)
        assert "title" not in og


# ===========================================================================
# cog — on_message routing (shared)
# ===========================================================================


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
