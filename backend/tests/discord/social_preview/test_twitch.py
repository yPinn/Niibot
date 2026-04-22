"""Tests for Twitch URL patterns, embed builders, and cog handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.cogs.social_preview import constants
from discord.cogs.social_preview.cog import SocialPreviewCog, _twitch_clip_mp4_url

from ._helpers import _make_message, aiter_bytes

# ===========================================================================
# constants — URL regex patterns
# ===========================================================================


class TestTwitchClipRE:
    RE = constants.TWITCH_CLIP_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://clips.twitch.tv/SlugHere",
            "http://clips.twitch.tv/SlugHere",
            "https://www.twitch.tv/channelname/clip/SlugHere",
            "https://twitch.tv/channelname/clip/SlugHere",
            "https://m.twitch.tv/channelname/clip/SlugHere",
            "https://m.twitch.tv/clip/SlugHere",
            "https://www.twitch.tv/clip/SlugHere",
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
# _twitch_clip_mp4_url helper
# ===========================================================================


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
# cog — _handle_twitch_clip (mocked HTTP)
# ===========================================================================


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

        assert msg.channel.send.await_count == 2
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

        msg.channel.send.assert_awaited_once()
