"""Unit tests for discord.cogs.social_preview.

Covers:
  - constants: URL regex patterns (match / no-match)
  - _embeds: per-platform embed builders
  - cog: _OGParser/_parse_og, platform handlers (mocked HTTP)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview._embeds import (
    build_bilibili_live_embed,
    build_instagram_profile_embed,
)
from discord.cogs.social_preview.cog import (
    SocialPreviewCog,
    _parse_og,
    _twitch_clip_mp4_url,
)
from discord.ext import commands

from core import EmbedFactory


async def aiter_bytes(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


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
            "https://m.instagram.com/p/Abc123/",
            "https://m.instagram.com/reel/XYZ789/",
            "https://instagr.am/p/Abc123/",
            "https://www.instagr.am/p/Abc123/",
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
        m = self.RE.search("https://www.instagram.com/reel/Abc123XYZ01/")
        assert m is not None
        assert m.group(1) == "reel"
        assert m.group(2) == "Abc123XYZ01"


class TestInstagramProfileRE:
    RE = constants.INSTAGRAM_PROFILE_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/testuser/",
            "https://instagram.com/testuser",
            "https://www.instagram.com/someuser/",
            "https://www.instagram.com/user.name_123/",
            "https://www.instagram.com/testuser/?hl=en",
            "https://m.instagram.com/testuser/",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/p/Abc123/",
            "https://www.instagram.com/reel/XYZ/",
            "https://www.instagram.com/tv/ABC/",
            "https://www.instagram.com/stories/user/123/",
            "https://www.instagram.com/explore/",
            "https://www.instagram.com/accounts/login/",
            "https://www.instagram.com/testuser/stories/highlight/123/",
            "https://twitter.com/someuser/",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    def test_captures_username(self) -> None:
        m = self.RE.search("https://www.instagram.com/testuser/")
        assert m is not None
        assert m.group(1) == "testuser"

    def test_post_url_not_matched_when_instagram_re_would_match(self) -> None:
        # Confirms INSTAGRAM_RE catches posts before profile RE is reached.
        url = "https://www.instagram.com/p/Abc123/"
        assert constants.INSTAGRAM_RE.search(url) is not None
        assert self.RE.search(url) is None


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
            "https://m.bilibili.com/video/BV1xx411c7mD",
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
        # No spaces → falls through to hard char-boundary cut at limit-1 + "…"
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
        # Text with a space near the limit — should cut at last space, not mid-word
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
        assert "B" not in embed.description  # cut before the B block

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
            "owner": {"mid": 12345, "name": "Creator", "face": "https://img.com/avatar.jpg"},
            "stat": {"view": 1000, "like": 500, "coin": 100, "favorite": 200, "share": 50},
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

    def test_author_url_links_to_space(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.author.url == "https://space.bilibili.com/12345"

    def test_author_url_absent_when_no_mid(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["owner"] = {"name": "Creator", "face": "https://img.com/avatar.jpg"}
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert not embed.author.url

    def test_metrics_layout(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        # row 1: 播放 + 分享 + spacer (inline x3), row 2: engagement (inline x3)
        assert len(embed.fields) == 6
        assert embed.fields[0].name == "播放"
        assert embed.fields[0].inline
        assert embed.fields[1].name == "分享"
        assert embed.fields[1].inline
        assert embed.fields[2].name == "\u200b"  # spacer
        assert embed.fields[2].inline
        assert embed.fields[3].name == "點讚"
        assert embed.fields[3].inline
        assert embed.fields[4].name == "投幣"
        assert embed.fields[4].inline
        assert embed.fields[5].name == "收藏"
        assert embed.fields[5].inline

    def test_view_count_uses_compact_format(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.fields[0].value == "1.0K"  # 播放 is fields[0]

    def test_share_absent_when_zero(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["stat"]["share"] = 0
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert all(f.name != "分享" for f in embed.fields)

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

    def test_footer_defers_to_factory(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        # use_platform_footer=False — factory config (empty in tests) drives footer
        assert embed.footer.text != "Bilibili"

    def test_image_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.image.url == "https://img.com/v.jpg"


class TestBuildBilibiliSpaceEmbed:
    _SPACE_URL = "https://space.bilibili.com/12345678"

    def _data(self) -> dict:
        return {
            "card": {
                "mid": "12345678",
                "name": "Test User",
                "face": "https://img.com/avatar.jpg",
                "sign": "A short bio.",
                "fans": 79803,
                "attention": 743,
            },
            "archive_count": 275,
        }

    def test_no_title(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        assert embed.title is None

    def test_author_name_and_icon(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        assert embed.author.name == "Test User"
        assert embed.author.icon_url == "https://img.com/avatar.jpg"
        assert embed.author.url == self._SPACE_URL

    def test_description_is_sign(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        assert "bio" in embed.description

    def test_stats_fields(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        names = [f.name for f in embed.fields]
        assert "粉絲" in names
        assert "關注" in names
        assert "影片" in names

    def test_fans_compact_format(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        fans_field = next(f for f in embed.fields if f.name == "粉絲")
        assert fans_field.value == "79.8K"


class TestBilibiliSpaceRegex:
    RE = constants.BILIBILI_SPACE_RE

    def test_matches(self) -> None:
        assert self.RE.search("https://space.bilibili.com/12345678") is not None

    def test_captures_mid(self) -> None:
        m = self.RE.search("https://space.bilibili.com/12345678")
        assert m is not None
        assert m.group(1) == "12345678"

    def test_no_match_on_video_url(self) -> None:
        assert self.RE.search("https://www.bilibili.com/video/BV1xx") is None


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


class TestTwitchClipRE:
    RE = constants.TWITCH_CLIP_RE

    @pytest.mark.parametrize(
        "url",
        [
            # clips.twitch.tv
            "https://clips.twitch.tv/SlugHere",
            "http://clips.twitch.tv/SlugHere",
            # www.twitch.tv with channel
            "https://www.twitch.tv/channelname/clip/SlugHere",
            "https://twitch.tv/channelname/clip/SlugHere",
            # mobile
            "https://m.twitch.tv/channelname/clip/SlugHere",
            "https://m.twitch.tv/clip/SlugHere",
            # no channel name (newer format)
            "https://www.twitch.tv/clip/SlugHere",
            # with tracking params (regex stops before ?)
            "https://clips.twitch.tv/SlugHere?tt_content=watchbutton&tt_medium=broadcast_chat",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://twitch.tv/channelname",
            "https://twitch.tv/channelname/videos/123456789",
            "https://twitch.tv/channelname/clips",
            "https://nottwitch.tv/clip/SlugHere",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    @pytest.mark.parametrize(
        ("url", "expected_slug"),
        [
            ("https://clips.twitch.tv/AmazingSlug", "AmazingSlug"),
            ("https://www.twitch.tv/channel/clip/AmazingSlug", "AmazingSlug"),
            ("https://m.twitch.tv/clip/AmazingSlug", "AmazingSlug"),
            ("https://clips.twitch.tv/AmazingSlug?tt_content=x", "AmazingSlug"),
        ],
    )
    def test_captures_slug(self, url: str, expected_slug: str) -> None:
        m = self.RE.search(url)
        assert m is not None
        assert (m.group(1) or m.group(2)) == expected_slug


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
    # Sent messages live in the same channel — needed so _send_video_reply's
    # self.message.channel.send resolves to the same mock as msg.channel.send.
    msg.channel.send.return_value.channel = msg.channel
    msg.delete = AsyncMock()
    return msg


@pytest.fixture
def cog(embed_factory: EmbedFactory) -> SocialPreviewCog:
    bot = MagicMock(spec=commands.Bot)
    c = SocialPreviewCog.__new__(SocialPreviewCog)
    c.bot = bot
    c._embed = embed_factory
    c._http = AsyncMock()
    c._twitch_token = None
    c._twitch_token_exp = 0.0
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

    @pytest.mark.asyncio
    async def test_video_post_uploads_file(self, cog: SocialPreviewCog) -> None:
        """Video posts (/p/): /images/ thumbnail + successful /videos/ probe → sends file."""
        og_html = (
            '<meta property="og:title" content="User on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        video_bytes = b"\x00\x01\x02"

        img_redir = self._make_redirect_resp(cdn_url)
        vid_redir = self._make_redirect_resp("https://scontent.cdninstagram.com/v.mp4")

        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()

        async def _aiter_bytes(_chunk_size):
            yield video_bytes

        stream_resp.aiter_bytes = _aiter_bytes
        stream_resp.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_resp.__aexit__ = AsyncMock(return_value=False)

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), img_redir, vid_redir])
        cog._http.stream = MagicMock(return_value=stream_resp)

        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)

        # Two sends: first embed, then video file as separate follow-up.
        assert msg.channel.send.await_count == 2
        first_kwargs = msg.channel.send.call_args_list[0].kwargs
        second_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert "embed" in first_kwargs
        assert second_kwargs.get("file") is not None

    @pytest.mark.asyncio
    async def test_photo_post_sends_embed_without_file(self, cog: SocialPreviewCog) -> None:
        """Photo posts: /videos/ probe fails → embed sent once, no video follow-up."""
        og_html = (
            '<meta property="og:title" content="User on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        img_redir = self._make_redirect_resp(cdn_url)
        # Video probe returns 200 (not a redirect) → no video downloaded
        no_redir = MagicMock()
        no_redir.is_redirect = False

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), img_redir, no_redir])

        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)

        # Only one send: embed only, no video follow-up.
        msg.channel.send.assert_awaited_once()
        assert "embed" in msg.channel.send.call_args.kwargs

    @pytest.mark.asyncio
    async def test_reel_uploads_video_file(self, cog: SocialPreviewCog) -> None:
        """Reels: embed sent first, then video as separate follow-up message."""
        og_html = (
            '<meta property="og:title" content="@jen3yu">'
            '<meta property="og:description" content="剪短ㄌ😗">'
            '<meta property="og:video" content="/videos/Abc123XYZ01/1">'
            '<meta property="og:video:type" content="video/mp4">'
        )
        video_bytes = b"\x00\x01\x02\x03"

        og_resp = self._make_og_resp(og_html)
        redir_resp = self._make_redirect_resp("https://scontent.cdninstagram.com/v.mp4")

        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()

        async def _aiter_bytes(_chunk_size):
            yield video_bytes

        stream_resp.aiter_bytes = _aiter_bytes
        stream_resp.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_resp.__aexit__ = AsyncMock(return_value=False)

        cog._http.get = AsyncMock(side_effect=[og_resp, redir_resp])
        cog._http.stream = MagicMock(return_value=stream_resp)

        msg = _make_message("https://www.instagram.com/reel/Abc123XYZ01/")
        await cog.on_message(msg)

        # Two sends: embed first, then video file.
        assert msg.channel.send.await_count == 2
        assert "embed" in msg.channel.send.call_args_list[0].kwargs
        second_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert second_kwargs.get("file") is not None
        assert second_kwargs["file"].filename == "reel.mp4"

    @pytest.mark.asyncio
    async def test_reel_falls_back_to_text_embed_when_video_too_large(
        self, cog: SocialPreviewCog
    ) -> None:
        """Reels: if video exceeds size limit, sends text-only embed without file."""
        og_html = (
            '<meta property="og:title" content="@jen3yu">'
            '<meta property="og:video" content="/videos/Abc123XYZ01/1">'
        )
        redir_resp = self._make_redirect_resp("https://scontent.cdninstagram.com/v.mp4")

        oversized_chunk = b"x" * (constants.VIDEO_MAX_BYTES + 1)
        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()

        async def _aiter_bytes(_chunk_size):
            yield oversized_chunk

        stream_resp.aiter_bytes = _aiter_bytes
        stream_resp.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_resp.__aexit__ = AsyncMock(return_value=False)

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), redir_resp])
        cog._http.stream = MagicMock(return_value=stream_resp)

        msg = _make_message("https://www.instagram.com/reel/Abc123XYZ01/")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        call_kwargs = msg.channel.send.call_args.kwargs
        assert call_kwargs.get("file") is None  # fallback: no file

    @pytest.mark.asyncio
    async def test_carousel_with_mixed_video(self, cog: SocialPreviewCog) -> None:
        """Carousel (/grid/): items include a video; first item sent with its video file."""
        og_html = '<meta property="og:image" content="/grid/ABC">'
        # img_index=1: image + video; img_index=2: image only; img_index=3,4: no result
        idx1_html = (
            '<meta property="og:title" content="@user">'
            '<meta property="og:image" content="/images/ABC/1">'
        )
        idx2_html = '<meta property="og:image" content="/images/ABC/2">'

        img_cdn = "https://scontent.cdninstagram.com/img.jpg"
        vid_cdn = "https://scontent.cdninstagram.com/v.mp4"

        og_resp = self._make_og_resp(og_html)
        idx1_og = self._make_og_resp(idx1_html)
        img1_redir = self._make_redirect_resp(img_cdn)
        vid1_redir = self._make_redirect_resp(vid_cdn)
        idx2_og = self._make_og_resp(idx2_html)
        img2_redir = self._make_redirect_resp(img_cdn)
        # idx2 video probe: no video
        no_redir = MagicMock()
        no_redir.is_redirect = False
        # idx3, idx4 return empty OG → no image redirect; video probe: no video
        empty = self._make_og_resp("<html></html>")

        video_bytes = b"\x00\x01"
        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()

        async def _aiter_bytes(_chunk_size):
            yield video_bytes

        stream_resp.aiter_bytes = _aiter_bytes
        stream_resp.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_resp.__aexit__ = AsyncMock(return_value=False)

        cog._http.get = AsyncMock(
            side_effect=[
                og_resp,  # /grid/ OG
                idx1_og,  # img_index=1 OG
                img1_redir,  # /images/ABC/1 redirect
                vid1_redir,  # /videos/ABC/1 redirect (has video)
                idx2_og,  # img_index=2 OG
                img2_redir,  # /images/ABC/2 redirect
                no_redir,  # /videos/ABC/2 (no video)
                empty,  # img_index=3 OG (empty)
                no_redir,  # /videos/ABC/3 (no video)
                empty,  # img_index=4 OG (empty)
                no_redir,  # /videos/ABC/4 (no video)
            ]
        )
        cog._http.stream = MagicMock(return_value=stream_resp)

        msg = _make_message("https://www.instagram.com/p/ABC/")
        await cog.on_message(msg)

        # Two sends: embed with carousel view first, then video file as follow-up.
        assert msg.channel.send.await_count == 2
        first_kwargs = msg.channel.send.call_args_list[0].kwargs
        second_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert first_kwargs.get("view") is not None  # carousel view on embed message
        assert "embed" in first_kwargs
        assert second_kwargs.get("file") is not None  # video sent separately
        # Videos are pre-downloaded into the view — no download callable
        view = first_kwargs["view"]
        assert hasattr(view, "_video_bytes")
        assert 0 in view._video_bytes  # item 0 has video bytes cached


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


class TestBuildInstagramProfileEmbed:
    def test_parses_display_name_from_bullet_format(self, embed_factory: EmbedFactory) -> None:
        og = {"title": "tpy ♥ she/her (@testuser) • Instagram photos and videos"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "testuser", "https://instagram.com/testuser/"
        )
        assert embed.title == "tpy ♥ she/her"

    def test_parses_display_name_without_handle_in_parens(
        self, embed_factory: EmbedFactory
    ) -> None:
        og = {"title": "Display Name • Instagram photos and videos"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "handle", "https://instagram.com/handle/"
        )
        assert embed.title == "Display Name"

    def test_falls_back_to_at_username_when_no_og_title(self, embed_factory: EmbedFactory) -> None:
        embed = build_instagram_profile_embed(
            embed_factory, {}, "testuser", "https://instagram.com/testuser/"
        )
        assert embed.title == "@testuser"

    def test_image_set_from_og(self, embed_factory: EmbedFactory) -> None:
        og = {"title": "User", "image": "https://img.com/avatar.jpg"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "user", "https://instagram.com/user/"
        )
        assert embed.image.url == "https://img.com/avatar.jpg"

    def test_description_set(self, embed_factory: EmbedFactory) -> None:
        og = {"title": "User", "description": "51 posts, 4.6K followers"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "user", "https://instagram.com/user/"
        )
        assert embed.description == "51 posts, 4.6K followers"

    def test_author_is_instagram(self, embed_factory: EmbedFactory) -> None:
        embed = build_instagram_profile_embed(
            embed_factory, {"title": "User"}, "user", "https://instagram.com/user/"
        )
        assert embed.author.name == "Instagram"


class TestBuildInstagramProfileEmbedStats:
    def _user_og(self) -> dict:
        return {
            "title": "tpy ♥ she/her",
            "description": "電影角色",
            "image": "https://scontent.cdninstagram.com/avatar.jpg",
        }

    def test_adds_posts_followers_following_fields(self, embed_factory: EmbedFactory) -> None:
        embed = build_instagram_profile_embed(
            embed_factory,
            self._user_og(),
            "testuser",
            "https://instagram.com/testuser/",
            posts=51,
            followers=46200,
            following=532,
        )
        field_names = [f.name for f in embed.fields]
        assert field_names == ["Posts", "Followers", "Following"]

    def test_followers_formatted_as_compact(self, embed_factory: EmbedFactory) -> None:
        embed = build_instagram_profile_embed(
            embed_factory,
            self._user_og(),
            "testuser",
            "https://instagram.com/testuser/",
            followers=46200,
        )
        assert embed.fields[0].value == "46.2K"

    def test_no_fields_when_stats_absent(self, embed_factory: EmbedFactory) -> None:
        embed = build_instagram_profile_embed(
            embed_factory,
            self._user_og(),
            "testuser",
            "https://instagram.com/testuser/",
        )
        assert embed.fields == []


class TestCogInstagramProfile:
    def _make_api_resp(self, user: dict) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"data": {"user": user}})
        return resp

    def _make_api_error(self) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock(side_effect=Exception("404"))
        resp.json = MagicMock(return_value={})
        return resp

    def _user_data(self) -> dict:
        return {
            "full_name": "tpy ♥ she/her",
            "biography": "電影角色",
            "profile_pic_url_hd": "https://scontent.cdninstagram.com/avatar.jpg",
            "edge_owner_to_timeline_media": {"count": 51},
            "edge_followed_by": {"count": 46200},
            "edge_follow": {"count": 532},
        }

    @pytest.mark.asyncio
    async def test_sends_rich_embed_via_api(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_api_resp(self._user_data()))
        msg = _make_message("https://www.instagram.com/testuser/")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.title == "tpy ♥ she/her"
        assert embed.image.url == "https://scontent.cdninstagram.com/avatar.jpg"
        field_names = [f.name for f in embed.fields]
        assert field_names == ["Posts", "Followers", "Following"]

    @pytest.mark.asyncio
    async def test_followers_count_formatted(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_api_resp(self._user_data()))
        msg = _make_message("https://www.instagram.com/testuser/")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        followers_field = next(f for f in embed.fields if f.name == "Followers")
        assert followers_field.value == "46.2K"

    @pytest.mark.asyncio
    async def test_sends_minimal_embed_when_api_fails(self, cog: SocialPreviewCog) -> None:
        """When the API fails, a minimal embed with @username is still sent."""
        cog._http.get = AsyncMock(return_value=self._make_api_error())
        msg = _make_message("https://www.instagram.com/testuser/")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.title == "@testuser"
        assert embed.fields == []

    @pytest.mark.asyncio
    async def test_post_url_not_handled_as_profile(self, cog: SocialPreviewCog) -> None:
        """Ensures post URLs are routed to _handle_instagram, not _handle_instagram_profile."""
        og_html = (
            '<meta property="og:title" content="User on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"

        def _make_og_resp(text: str) -> MagicMock:
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.is_redirect = False
            r.text = text
            return r

        cog._http.get = AsyncMock(
            side_effect=[
                _make_og_resp(og_html),
                MagicMock(is_redirect=True, headers={"location": cdn_url}),
                MagicMock(is_redirect=False),  # video probe
            ]
        )
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)
        embed = msg.channel.send.call_args_list[0].kwargs["embed"]
        assert embed.title == "User"

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(return_value=self._make_api_resp(self._user_data()))
        msg = _make_message("https://www.instagram.com/someuser/")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()


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


class TestCogTwitchClip:
    """Tests for _handle_twitch_clip.

    Token management is bypassed by pre-injecting a valid token so tests only
    exercise the Helix API path and embed assembly.
    """

    def _clip_data(self, **overrides: object) -> dict:
        base: dict = {
            "id": "AbcDef123",
            "url": "https://clips.twitch.tv/AbcDef123",
            "title": "Amazing Play",
            "broadcaster_name": "StreamerNii",
            "creator_name": "ClipMaker",
            "thumbnail_url": "https://clips.twitch.tv/AbcDef123-preview.jpg",
            "view_count": 12345,
            "duration": 30.5,
        }
        base.update(overrides)
        return base

    def _make_clips_resp(self, clips: list[dict]) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"data": clips})
        return resp

    def _inject_token(self, cog: SocialPreviewCog) -> None:
        """Pre-seed a non-expiring token so _get_twitch_token skips the OAuth call."""
        cog._twitch_token = "test_token"
        cog._twitch_token_exp = float("inf")

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(return_value=self._make_clips_resp([self._clip_data()]))
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.title == "Amazing Play"
        assert embed.author.name == "StreamerNii"

    @pytest.mark.asyncio
    async def test_channel_clip_url_format(self, cog: SocialPreviewCog) -> None:
        """twitch.tv/<channel>/clip/<slug> URL is handled the same as clips.twitch.tv/<slug>."""
        self._inject_token(cog)
        cog._http.get = AsyncMock(return_value=self._make_clips_resp([self._clip_data()]))
        msg = _make_message("https://www.twitch.tv/streamer/clip/AbcDef123")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(return_value=self._make_clips_resp([self._clip_data()]))
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_send_on_empty_data(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(return_value=self._make_clips_resp([]))
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_send_on_api_error(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_send_without_credentials(self, cog: SocialPreviewCog) -> None:
        """If no Twitch credentials are configured, handler silently does nothing."""
        # Do NOT inject token — cog has _twitch_token=None, _twitch_token_exp=0
        cog._get_twitch_token = AsyncMock(return_value=None)
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embed_duration_format(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(
            return_value=self._make_clips_resp([self._clip_data(duration=90.0)])
        )
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        field_values = [f.value for f in embed.fields]
        assert any("1:30" in v for v in field_values)

    @pytest.mark.asyncio
    async def test_embed_has_view_count_field(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(
            return_value=self._make_clips_resp([self._clip_data(view_count=12345)])
        )
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "觀看次數" in field_names

    @pytest.mark.asyncio
    async def test_embed_has_creator_and_date_fields(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        cog._http.get = AsyncMock(
            return_value=self._make_clips_resp(
                [self._clip_data(creator_name="ClipMaker", created_at="2024-03-15T10:00:00Z")]
            )
        )
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        fields = {f.name: f.value for f in embed.fields}
        assert fields.get("剪輯作者") == "ClipMaker"
        assert fields.get("剪輯時間") == "2024-03-15"

    @pytest.mark.asyncio
    async def test_broadcaster_avatar_and_url_from_users_api(self, cog: SocialPreviewCog) -> None:
        self._inject_token(cog)
        avatar_url = "https://static-cdn.jtvnw.net/jtv_user_pictures/streamer-300x300.png"
        users_resp = MagicMock()
        users_resp.raise_for_status = MagicMock()
        users_resp.json = MagicMock(
            return_value={"data": [{"profile_image_url": avatar_url, "login": "streamernii"}]}
        )
        cog._http.get = AsyncMock(
            side_effect=[self._make_clips_resp([self._clip_data(broadcaster_id="123")]), users_resp]
        )
        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.icon_url == avatar_url
        assert embed.author.url == "https://twitch.tv/streamernii"

    @pytest.mark.asyncio
    async def test_uploads_mp4_when_available(self, cog: SocialPreviewCog) -> None:
        """When the CDN MP4 is reachable and within size limit, it is uploaded as a file."""
        self._inject_token(cog)
        thumb = "https://clips-media-assets2.twitch.tv/AbcHash-preview-480x272.jpg"
        cog._http.get = AsyncMock(
            return_value=self._make_clips_resp([self._clip_data(thumbnail_url=thumb)])
        )
        mp4_bytes = b"\x00" * 1024
        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()
        stream_resp.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_resp.__aexit__ = AsyncMock(return_value=False)
        stream_resp.aiter_bytes = MagicMock(return_value=aiter_bytes([mp4_bytes]))
        cog._http.stream = MagicMock(return_value=stream_resp)

        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        assert msg.channel.send.await_count == 2  # embed + file follow-up
        file_call_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert file_call_kwargs.get("file") is not None
        assert file_call_kwargs["file"].filename == "clip.mp4"

    @pytest.mark.asyncio
    async def test_falls_back_to_embed_when_mp4_fails(self, cog: SocialPreviewCog) -> None:
        """When the CDN MP4 download fails, the embed is still sent without a file."""
        self._inject_token(cog)
        thumb = "https://clips-media-assets2.twitch.tv/AbcHash-preview-480x272.jpg"
        cog._http.get = AsyncMock(
            return_value=self._make_clips_resp([self._clip_data(thumbnail_url=thumb)])
        )
        stream_resp = MagicMock()
        stream_resp.__aenter__ = AsyncMock(side_effect=Exception("CDN error"))
        stream_resp.__aexit__ = AsyncMock(return_value=False)
        cog._http.stream = MagicMock(return_value=stream_resp)

        msg = _make_message("https://clips.twitch.tv/AbcDef123")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()  # embed only, no file follow-up


class TestTwitchClipMp4Url:
    def test_standard_pattern(self) -> None:
        thumb = "https://clips-media-assets2.twitch.tv/AbcHash-preview-480x272.jpg"
        assert _twitch_clip_mp4_url(thumb) == "https://clips-media-assets2.twitch.tv/AbcHash.mp4"

    def test_at_cm_pattern(self) -> None:
        thumb = "https://clips-media-assets2.twitch.tv/AT-cm%7CAbcHash-preview-480x272.jpg"
        assert (
            _twitch_clip_mp4_url(thumb)
            == "https://clips-media-assets2.twitch.tv/AT-cm%7CAbcHash.mp4"
        )

    def test_different_resolution(self) -> None:
        thumb = "https://clips-media-assets2.twitch.tv/Hash-preview-1920x1080.jpg"
        assert _twitch_clip_mp4_url(thumb) == "https://clips-media-assets2.twitch.tv/Hash.mp4"

    def test_returns_none_for_empty(self) -> None:
        assert _twitch_clip_mp4_url("") is None

    def test_returns_none_for_non_matching_url(self) -> None:
        assert _twitch_clip_mp4_url("https://example.com/image.jpg") is None


# ===========================================================================
# constants — BILIBILI_LIVE_RE
# ===========================================================================


class TestBilibiliLiveRE:
    RE = constants.BILIBILI_LIVE_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://live.bilibili.com/22628755",
            "http://live.bilibili.com/22628755",
            # query params from share links
            "https://live.bilibili.com/22628755?live_from=71002&visit_id=7zfa8lxfv1s0",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://space.bilibili.com/12345",
            "https://live.bilibili.com/",
            "https://notbilibili.com/live/123",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    def test_captures_room_id(self) -> None:
        m = self.RE.search("https://live.bilibili.com/22628755?live_from=71002")
        assert m is not None
        assert m.group(1) == "22628755"


# ===========================================================================
# _embeds — build_bilibili_live_embed
# ===========================================================================


class TestBuildBilibiliLiveEmbed:
    _ROOM_URL = "https://live.bilibili.com/22628755"

    def _room(self, **overrides: object) -> dict:
        base: dict = {
            "uid": 26433952,
            "room_id": 22628755,
            "title": "IEM里约2026",
            "live_status": 1,
            "online": 14523,
            "attention": 684212,
            "area_name": "英雄聯盟",
            "parent_area_name": "遊戲",
            "live_time": "2026-04-20 20:30:00",
            "user_cover": "https://i2.hdslb.com/bfs/live/cover.jpg",
            "keyframe": "https://i2.hdslb.com/bfs/live/keyframe.jpg",
        }
        base.update(overrides)
        return base

    def _card_data(self) -> dict:
        return {
            "card": {
                "mid": "26433952",
                "name": "張立友",
                "face": "https://i2.hdslb.com/bfs/face/avatar.jpg",
            }
        }

    def test_title_set(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert embed.title == "IEM里约2026"

    def test_status_field_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=1), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "狀態").value == "直播中"

    def test_status_field_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "狀態").value == "下播"

    def test_status_field_rotating(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=2), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "狀態").value == "輪播"

    def test_area_field(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "分類").value == "英雄聯盟"

    def test_viewer_count_only_when_live(self, embed_factory: EmbedFactory) -> None:
        live_embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, online=14523),
            self._card_data(),
            self._ROOM_URL,
        )
        offline_embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0, online=0), self._card_data(), self._ROOM_URL
        )
        assert any(f.name == "觀看人數" for f in live_embed.fields)
        assert not any(f.name == "觀看人數" for f in offline_embed.fields)

    def test_viewer_count_compact_format(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, online=14523),
            self._card_data(),
            self._ROOM_URL,
        )
        assert next(f for f in embed.fields if f.name == "觀看人數").value == "14.5K"

    def test_keyframe_used_as_image_when_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=1), self._card_data(), self._ROOM_URL
        )
        assert embed.image.url == "https://i2.hdslb.com/bfs/live/keyframe.jpg"

    def test_user_cover_used_when_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0), self._card_data(), self._ROOM_URL
        )
        assert embed.image.url == "https://i2.hdslb.com/bfs/live/cover.jpg"

    def test_author_name_from_card(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert embed.author.name == "張立友"

    def test_author_url_links_to_space(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert embed.author.url == "https://space.bilibili.com/26433952"

    def test_no_card_data_still_builds(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(embed_factory, self._room(), None, self._ROOM_URL)
        assert isinstance(embed, discord.Embed)
        assert embed.author.name is None

    def test_area_falls_back_to_parent(self, embed_factory: EmbedFactory) -> None:
        room = self._room()
        del room["area_name"]
        embed = build_bilibili_live_embed(embed_factory, room, None, self._ROOM_URL)
        area = next((f for f in embed.fields if f.name == "分類"), None)
        assert area is not None
        assert area.value == "遊戲"

    def test_no_area_field_when_absent(self, embed_factory: EmbedFactory) -> None:
        room = self._room()
        del room["area_name"]
        del room["parent_area_name"]
        embed = build_bilibili_live_embed(embed_factory, room, None, self._ROOM_URL)
        assert not any(f.name == "分類" for f in embed.fields)

    # ── 開播時間 ────────────────────────────────────────────────────────────────

    def test_live_time_shown_when_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, live_time="2026-04-20 20:30:00"),
            self._card_data(),
            self._ROOM_URL,
        )
        assert any(f.name == "開播時間" for f in embed.fields)
        assert next(f for f in embed.fields if f.name == "開播時間").value == "20:30"

    def test_live_time_absent_when_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=0, live_time="0000-00-00 00:00:00"),
            self._card_data(),
            self._ROOM_URL,
        )
        assert not any(f.name == "開播時間" for f in embed.fields)

    def test_live_time_zero_sentinel_ignored(self, embed_factory: EmbedFactory) -> None:
        """live_time="0000-00-00 00:00:00" (offline sentinel) must not appear even when live."""
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, live_time="0000-00-00 00:00:00"),
            self._card_data(),
            self._ROOM_URL,
        )
        assert not any(f.name == "開播時間" for f in embed.fields)

    # ── 關注數 ──────────────────────────────────────────────────────────────────

    def test_attention_shown_when_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, attention=684212),
            self._card_data(),
            self._ROOM_URL,
        )
        assert any(f.name == "關注" for f in embed.fields)
        assert next(f for f in embed.fields if f.name == "關注").value == "684.2K"

    def test_attention_shown_when_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=0, attention=684212),
            self._card_data(),
            self._ROOM_URL,
        )
        assert any(f.name == "關注" for f in embed.fields)

    def test_attention_absent_when_zero(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(attention=0), self._card_data(), self._ROOM_URL
        )
        assert not any(f.name == "關注" for f in embed.fields)

    # ── Field grid layout ───────────────────────────────────────────────────────

    def test_live_full_layout_is_six_fields(self, embed_factory: EmbedFactory) -> None:
        """Row1: 狀態|分類|觀看人數  Row2: 開播時間|關注|spacer = 6 fields."""
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=1), self._card_data(), self._ROOM_URL
        )
        assert len(embed.fields) == 6
        assert embed.fields[5].name == "\u200b"  # spacer pads row 2 to 3

    def test_offline_full_layout_is_three_fields(self, embed_factory: EmbedFactory) -> None:
        """Row1: 狀態|分類|關注 = 3 fields, no spacer needed."""
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0), self._card_data(), self._ROOM_URL
        )
        assert len(embed.fields) == 3
        assert not any(f.name == "\u200b" for f in embed.fields)


# ===========================================================================
# cog — _handle_bilibili_live (mocked HTTP)
# ===========================================================================


class TestCogBilibiliLive:
    def _live_api_resp(self, **overrides: object) -> MagicMock:
        room: dict = {
            "uid": 26433952,
            "room_id": 22628755,
            "title": "IEM里约2026",
            "live_status": 1,
            "online": 14523,
            "attention": 684212,
            "area_name": "英雄聯盟",
            "live_time": "2026-04-20 20:30:00",
            "user_cover": "https://i2.hdslb.com/bfs/live/cover.jpg",
            "keyframe": "https://i2.hdslb.com/bfs/live/keyframe.jpg",
        }
        room.update(overrides)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"code": 0, "data": room})
        return resp

    def _card_api_resp(self) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(
            return_value={
                "code": 0,
                "data": {
                    "card": {
                        "mid": "26433952",
                        "name": "張立友",
                        "face": "https://i2.hdslb.com/bfs/face/avatar.jpg",
                    }
                },
            }
        )
        return resp

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message("https://live.bilibili.com/22628755")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.title == "IEM里约2026"

    @pytest.mark.asyncio
    async def test_share_url_with_query_params(self, cog: SocialPreviewCog) -> None:
        """URLs with ?live_from=...&visit_id=... are matched and room_id extracted correctly."""
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message(
            "https://live.bilibili.com/22628755?live_from=71002&visit_id=7zfa8lxfv1s0"
        )
        await cog.on_message(msg)
        msg.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message("https://live.bilibili.com/22628755")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_still_sent_when_card_api_fails(self, cog: SocialPreviewCog) -> None:
        """Card API failure degrades gracefully — embed sent without author name."""
        card_err = MagicMock()
        card_err.raise_for_status = MagicMock(side_effect=Exception("timeout"))
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), card_err])
        msg = _make_message("https://live.bilibili.com/22628755")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.name is None

    @pytest.mark.asyncio
    async def test_no_send_on_live_api_error(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message("https://live.bilibili.com/22628755")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_send_on_api_error_code(self, cog: SocialPreviewCog) -> None:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"code": -404, "data": None})
        cog._http.get = AsyncMock(return_value=resp)
        msg = _make_message("https://live.bilibili.com/22628755")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_offline_room_embed(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(
            side_effect=[self._live_api_resp(live_status=0, online=0), self._card_api_resp()]
        )
        msg = _make_message("https://live.bilibili.com/22628755")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        status = next(f for f in embed.fields if f.name == "狀態")
        assert status.value == "下播"
        assert not any(f.name == "觀看人數" for f in embed.fields)
