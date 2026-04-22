"""Tests for TikTok URL patterns, embed builders, and cog handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview.cog import SocialPreviewCog

from core import EmbedFactory

from ._helpers import _make_message

# ===========================================================================
# constants — URL regex patterns
# ===========================================================================


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
# _embeds — TikTok embed builder
# ===========================================================================


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
# cog — _handle_tiktok (mocked HTTP)
# ===========================================================================


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
