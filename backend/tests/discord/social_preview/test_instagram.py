"""Tests for Instagram URL patterns, embed builders, and cog handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview._embeds import build_instagram_profile_embed
from discord.cogs.social_preview.cog import SocialPreviewCog

from core import EmbedFactory

from ._helpers import _make_message

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
        url = "https://www.instagram.com/p/Abc123/"
        assert constants.INSTAGRAM_RE.search(url) is not None
        assert self.RE.search(url) is None


# ===========================================================================
# _embeds — Instagram embed builders
# ===========================================================================


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
        embed = embeds_mod.build_instagram_embed(
            embed_factory,
            {"title": "@testuser_reel", "description": "caption"},
            "https://example.com",
        )
        assert embed.title == "@testuser_reel"

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
        embed = embeds_mod.build_instagram_embed(embed_factory, self._og(), "https://example.com")
        assert embed.footer.text is None

    def test_empty_og_does_not_raise(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_instagram_embed(embed_factory, {}, "https://example.com")
        assert isinstance(embed, discord.Embed)


class TestBuildInstagramProfileEmbed:
    def test_parses_display_name_from_bullet_format(self, embed_factory: EmbedFactory) -> None:
        og = {"title": "Test User (@testuser) • Instagram photos and videos"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "testuser", "https://instagram.com/testuser/"
        )
        assert embed.title == "Test User (@testuser)"

    def test_parses_display_name_without_handle_in_parens(
        self, embed_factory: EmbedFactory
    ) -> None:
        og = {"title": "Display Name • Instagram photos and videos"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "handle", "https://instagram.com/handle/"
        )
        assert embed.title == "Display Name (@handle)"

    def test_falls_back_to_at_username_when_no_og_title(self, embed_factory: EmbedFactory) -> None:
        embed = build_instagram_profile_embed(
            embed_factory, {}, "testuser", "https://instagram.com/testuser/"
        )
        assert embed.title == "@testuser"

    def test_image_set_as_thumbnail(self, embed_factory: EmbedFactory) -> None:
        og = {"title": "User", "image": "https://img.com/avatar.jpg"}
        embed = build_instagram_profile_embed(
            embed_factory, og, "user", "https://instagram.com/user/"
        )
        assert embed.thumbnail.url == "https://img.com/avatar.jpg"
        assert embed.image.url is None

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
            "title": "Test User",
            "description": "A short bio.",
            "image": "https://example.com/avatar.jpg",
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


# ===========================================================================
# cog — _handle_instagram / _handle_instagram_profile (mocked HTTP)
# ===========================================================================


class TestCogInstagram:
    @pytest.fixture(autouse=True)
    def _without_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = MagicMock()
        settings.instagram_session_id = ""
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: settings)

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
        assert embed.footer.text is None

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
            '<meta property="og:title" content="testuser_ig on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        cog._http.get = AsyncMock(side_effect=self._default_side_effects(og_html, cdn_url))
        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.name == "Instagram"
        assert embed.author.url == "https://www.instagram.com/p/Abc123/"
        assert embed.title == "testuser_ig"

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

        assert msg.channel.send.await_count == 2
        first_kwargs = msg.channel.send.call_args_list[0].kwargs
        second_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert "embed" in first_kwargs
        assert second_kwargs.get("files") is not None
        assert len(second_kwargs["files"]) == 1

    @pytest.mark.asyncio
    async def test_photo_post_sends_embed_without_file(self, cog: SocialPreviewCog) -> None:
        """Photo posts: /videos/ probe fails → embed sent once, no video follow-up."""
        og_html = (
            '<meta property="og:title" content="User on Instagram">'
            '<meta property="og:image" content="/images/Abc123/1">'
        )
        cdn_url = "https://scontent.cdninstagram.com/img.jpg"
        img_redir = self._make_redirect_resp(cdn_url)
        no_redir = MagicMock()
        no_redir.is_redirect = False

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), img_redir, no_redir])

        msg = _make_message("https://www.instagram.com/p/Abc123/")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        assert "embed" in msg.channel.send.call_args.kwargs

    @pytest.mark.asyncio
    async def test_reel_uploads_video_file(self, cog: SocialPreviewCog) -> None:
        """Reels: embed sent first, then video as separate follow-up message."""
        og_html = (
            '<meta property="og:title" content="@testuser_reel">'
            '<meta property="og:description" content="Test caption">'
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

        assert msg.channel.send.await_count == 2
        assert "embed" in msg.channel.send.call_args_list[0].kwargs
        second_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert second_kwargs.get("files") is not None
        assert len(second_kwargs["files"]) == 1
        assert second_kwargs["files"][0].filename == "reel.mp4"

    @pytest.mark.asyncio
    async def test_reel_falls_back_to_text_embed_when_video_too_large(
        self, cog: SocialPreviewCog
    ) -> None:
        """Reels: if video exceeds size limit, sends text-only embed without file."""
        og_html = (
            '<meta property="og:title" content="@testuser_reel">'
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
        assert call_kwargs.get("file") is None

    @pytest.mark.asyncio
    async def test_carousel_with_mixed_video(self, cog: SocialPreviewCog) -> None:
        """Carousel (/grid/): photos shown in embed, videos sent as bundled reply files."""
        og_html = '<meta property="og:image" content="/grid/ABC">'
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
        no_redir = MagicMock()
        no_redir.is_redirect = False
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

        # item1=(img,vid), item2=(img,None) → photo_items=[item2], video_cdns=[vid1]
        # 1 photo item → plain embed (no carousel view), videos bundled as files= reply
        assert msg.channel.send.await_count == 2
        first_kwargs = msg.channel.send.call_args_list[0].kwargs
        second_kwargs = msg.channel.send.call_args_list[1].kwargs
        assert "embed" in first_kwargs
        assert first_kwargs.get("view") is None
        assert second_kwargs.get("files") is not None
        assert len(second_kwargs["files"]) == 1
        assert second_kwargs["files"][0].filename == "reel.mp4"


class TestCogInstagramProfile:
    @pytest.fixture(autouse=True)
    def _with_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = MagicMock()
        settings.instagram_session_id = "test_session"
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: settings)

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
            "full_name": "Test User",
            "biography": "A short bio.",
            "profile_pic_url_hd": "https://example.com/avatar.jpg",
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
        assert embed.title == "Test User (@testuser)"
        assert embed.thumbnail.url == "https://example.com/avatar.jpg"
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
                MagicMock(is_redirect=False),
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


class TestCogInstagramProfileNoSession:
    @pytest.fixture(autouse=True)
    def _without_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = MagicMock()
        settings.instagram_session_id = ""
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: settings)

    @pytest.mark.asyncio
    async def test_ignores_profile_url_without_session(self, cog: SocialPreviewCog) -> None:
        """Without INSTAGRAM_SESSION_ID the profile handler silently does nothing."""
        msg = _make_message("https://www.instagram.com/testuser/")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()
