"""Tests for Threads URL patterns, embed builders, and cog handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview._embeds import get_threads_handle
from discord.cogs.social_preview.cog import SocialPreviewCog

from core import EmbedFactory

from ._helpers import _make_message

# ===========================================================================
# constants — URL regex patterns
# ===========================================================================


class TestThreadsRE:
    RE = constants.THREADS_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.threads.com/@user/post/AbcDef123",
            "https://threads.net/@user.name/post/XYZ",
            "https://www.threads.com/@user/post/AbcDef123",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.threads.com/@user",
            "https://threads.net/",
            "https://notthreads.net/@user/post/Abc",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None


# ===========================================================================
# _embeds — Threads embed builders
# ===========================================================================


class TestBuildThreadsEmbed:
    _POST_URL = "https://www.threads.com/@u/post/X"

    def _og(self) -> dict:
        return {
            "title": "ThreadsUser on Threads",
            "description": "Some post",
            "image": "https://img.com/t.jpg",
        }

    def _oembed(self) -> dict:
        return {
            "author_name": "threaduser",
            "author_url": "https://www.threads.com/@threaduser",
            "provider_name": "Threads",
        }

    # ── OG path ───────────────────────────────────────────────────────────────

    def test_og_author_row_is_threads_platform(self, embed_factory: EmbedFactory) -> None:
        """Author row always shows 'Threads' (platform identity, not user)."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._og(), self._POST_URL)
        assert embed.author.name == "Threads"

    def test_og_author_url_is_post_url(self, embed_factory: EmbedFactory) -> None:
        """Author icon (Threads brand) links to the post."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._og(), self._POST_URL)
        assert embed.author.url == self._POST_URL

    def test_og_embed_url_is_profile_url(self, embed_factory: EmbedFactory) -> None:
        """Title links to the author's profile, not the post."""
        data = {"title": "測試名 (@test_handle) on Threads"}
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.url == "https://www.threads.com/@test_handle"

    def test_og_embed_url_falls_back_to_post_when_no_handle(
        self, embed_factory: EmbedFactory
    ) -> None:
        """When handle cannot be parsed, title URL falls back to post URL."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._og(), self._POST_URL)
        assert embed.url == self._POST_URL

    def test_og_account_in_title(self, embed_factory: EmbedFactory) -> None:
        """Account display name is placed in the embed title."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._og(), self._POST_URL)
        assert embed.title == "ThreadsUser"

    def test_og_description_used(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(embed_factory, self._og(), self._POST_URL)
        assert embed.description == "Some post"

    def test_og_no_footer(self, embed_factory: EmbedFactory) -> None:
        """Platform shown in author row — footer must be empty."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._og(), self._POST_URL)
        assert not embed.footer.text

    def test_og_display_name_handle_in_title(self, embed_factory: EmbedFactory) -> None:
        """Discordbot UA 'DisplayName (@handle)' becomes the embed title."""
        data = {"title": "測試名 (@test_handle)", "image": "https://cdn.threads.net/img.jpg"}
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.title == "測試名 (@test_handle)"
        assert embed.author.name == "Threads"

    def test_og_display_name_handle_with_on_threads_suffix(
        self, embed_factory: EmbedFactory
    ) -> None:
        """Actual OG title format 'DisplayName (@handle) on Threads' is parsed correctly."""
        data = {
            "title": "測試名 (@test_handle) on Threads",
            "image": "https://cdn.threads.net/img.jpg",
        }
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.title == "測試名 (@test_handle)"
        assert embed.author.name == "Threads"

    def test_og_generic_desc_filtered(self, embed_factory: EmbedFactory) -> None:
        """'N Replies. See more…' CTA must be dropped."""
        data = {
            "title": "測試名 (@test_handle)",
            "description": "1.9K Replies. See more photos and videos by 測試名 on Threads.",
        }
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.description is None

    def test_og_real_description_kept(self, embed_factory: EmbedFactory) -> None:
        """Actual post captions must pass through."""
        data = {"title": "測試名 (@test_handle)", "description": "測試貼文內容。"}
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.description == "測試貼文內容。"

    def test_og_caption_with_cta_suffix_stripped(self, embed_factory: EmbedFactory) -> None:
        """Caption before stats CTA must be preserved; the CTA line must be dropped."""
        data = {
            "title": "測試名 (@test_handle)",
            "description": "測試貼文內容。\n1.9K Replies. See more photos and videos.",
        }
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.description == "測試貼文內容。"

    # ── oEmbed path ───────────────────────────────────────────────────────────

    def test_oembed_author_row_is_threads_platform(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(embed_factory, self._oembed(), self._POST_URL)
        assert embed.author.name == "Threads"

    def test_oembed_author_url_is_post_url(self, embed_factory: EmbedFactory) -> None:
        """Author icon links to the post."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._oembed(), self._POST_URL)
        assert embed.author.url == self._POST_URL

    def test_oembed_embed_url_is_profile_url(self, embed_factory: EmbedFactory) -> None:
        """Title links to the author's profile via oEmbed author_url."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._oembed(), self._POST_URL)
        assert embed.url == "https://www.threads.com/@threaduser"

    def test_oembed_account_in_title(self, embed_factory: EmbedFactory) -> None:
        """oEmbed author_name becomes the embed title."""
        embed = embeds_mod.build_threads_embed(embed_factory, self._oembed(), self._POST_URL)
        assert embed.title == "threaduser"

    def test_oembed_no_footer(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(embed_factory, self._oembed(), self._POST_URL)
        assert not embed.footer.text

    def test_oembed_no_description(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_threads_embed(embed_factory, self._oembed(), self._POST_URL)
        assert embed.description is None

    def test_oembed_thumbnail_used_as_image(self, embed_factory: EmbedFactory) -> None:
        data = {**self._oembed(), "thumbnail_url": "https://cdn.threads.net/thumb.jpg"}
        embed = embeds_mod.build_threads_embed(embed_factory, data, self._POST_URL)
        assert embed.image.url == "https://cdn.threads.net/thumb.jpg"


class TestGetThreadsHandle:
    def test_og_handle_extracted(self) -> None:
        data = {"title": "測試名 (@test_handle) on Threads"}
        assert get_threads_handle(data) == "test_handle"

    def test_og_handle_without_suffix(self) -> None:
        data = {"title": "測試名 (@test_handle)"}
        assert get_threads_handle(data) == "test_handle"

    def test_og_no_handle_returns_none(self) -> None:
        data = {"title": "ThreadsUser on Threads"}
        assert get_threads_handle(data) is None

    def test_oembed_handle_from_author_url(self) -> None:
        data = {"author_name": "test_handle", "author_url": "https://www.threads.com/@test_handle"}
        assert get_threads_handle(data) == "test_handle"

    def test_oembed_handle_with_trailing_slash(self) -> None:
        data = {"author_name": "test_handle", "author_url": "https://www.threads.com/@test_handle/"}
        assert get_threads_handle(data) == "test_handle"

    def test_oembed_missing_author_url_returns_none(self) -> None:
        data = {"author_name": "test_handle"}
        assert get_threads_handle(data) is None


# ===========================================================================
# cog — _handle_threads (mocked HTTP)
# ===========================================================================


class TestCogThreads:
    _MSG_URL = "https://www.threads.com/@threaduser/post/AbcDef123"

    def _make_oembed_resp(self, author_name: str = "threaduser") -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.is_redirect = False
        resp.headers = {"content-type": "application/json"}
        resp.json = MagicMock(
            return_value={
                "author_name": author_name,
                "author_url": f"https://www.threads.com/@{author_name}",
                "provider_name": "Threads",
            }
        )
        return resp

    def _make_og_resp(self, og_html: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.is_redirect = False
        resp.text = og_html
        return resp

    # ── bot-UA OG primary path ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sends_embed_via_bot_ua_og(self, cog: SocialPreviewCog) -> None:
        og_html = (
            '<meta property="og:title" content="ThreadsUser on Threads">'
            '<meta property="og:description" content="Great post">'
        )
        cog._http.get = AsyncMock(return_value=self._make_og_resp(og_html))
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.name == "Threads"
        assert embed.title == "ThreadsUser"

    @pytest.mark.asyncio
    async def test_bot_ua_og_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        og_html = '<meta property="og:title" content="User on Threads">'
        cog._http.get = AsyncMock(return_value=self._make_og_resp(og_html))
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    # ── oEmbed forward-compat fallback ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_falls_back_to_oembed_when_og_fails(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(
            side_effect=[self._make_og_resp(""), self._make_oembed_resp("threaduser")]
        )
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.name == "Threads"
        assert embed.title == "threaduser"

    @pytest.mark.asyncio
    async def test_no_send_when_both_fail(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    # ── scraper sidecar integration ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_scraper_caption_enriches_embed(
        self, cog: SocialPreviewCog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When scrapling_host is set, caption from scraper appears in description."""
        mock_settings = MagicMock()
        mock_settings.scrapling_host = "scrapling:3001"
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: mock_settings)
        og_html = '<meta property="og:title" content="User on Threads">'

        scraper_resp = MagicMock()
        scraper_resp.raise_for_status = MagicMock()
        scraper_resp.json = MagicMock(return_value={"caption": "Caption from Scrapling."})

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), scraper_resp])
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.description == "Caption from Scrapling."

    @pytest.mark.asyncio
    async def test_scraper_failure_does_not_block_embed(
        self, cog: SocialPreviewCog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scraper error is swallowed; embed is still sent without caption."""
        mock_settings = MagicMock()
        mock_settings.scrapling_host = "scrapling:3001"
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: mock_settings)
        og_html = (
            '<meta property="og:title" content="User on Threads">'
            '<meta property="og:description" content="Check out this link">'
        )

        cog._http.get = AsyncMock(
            side_effect=[self._make_og_resp(og_html), Exception("connection refused")]
        )
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scraper_skipped_when_host_not_configured(
        self, cog: SocialPreviewCog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When scrapling_host is empty, scraper is never called."""
        mock_settings = MagicMock()
        mock_settings.scrapling_host = ""
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: mock_settings)
        og_html = '<meta property="og:title" content="User on Threads">'
        cog._http.get = AsyncMock(return_value=self._make_og_resp(og_html))
        msg = _make_message(self._MSG_URL)
        await cog.on_message(msg)

        assert cog._http.get.await_count == 1
        msg.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scraper_empty_result_still_sends_embed(
        self,
        cog: SocialPreviewCog,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When scrapling returns all-empty values, embed still sends and a warning is logged."""
        import logging

        mock_settings = MagicMock()
        mock_settings.scrapling_host = "scrapling:3001"
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: mock_settings)
        og_html = '<meta property="og:title" content="User on Threads">'

        scraper_resp = MagicMock()
        scraper_resp.raise_for_status = MagicMock()
        scraper_resp.json = MagicMock(
            return_value={"caption": "", "image_urls": [], "video_urls": []}
        )

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), scraper_resp])
        msg = _make_message(self._MSG_URL)
        with caplog.at_level(logging.WARNING, logger="discord.cogs.social_preview.cog"):
            await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        assert any("empty result" in r.message or "no data" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_scraper_login_wall_warns_session_expired(
        self,
        cog: SocialPreviewCog,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When scrapling returns _reason=login_wall, a specific session-expired warning is logged."""
        import logging

        mock_settings = MagicMock()
        mock_settings.scrapling_host = "scrapling:3001"
        monkeypatch.setattr("discord.cogs.social_preview.cog.get_settings", lambda: mock_settings)
        og_html = '<meta property="og:title" content="User on Threads">'

        scraper_resp = MagicMock()
        scraper_resp.raise_for_status = MagicMock()
        scraper_resp.json = MagicMock(
            return_value={
                "caption": "",
                "image_urls": [],
                "video_urls": [],
                "_reason": "login_wall",
            }
        )

        cog._http.get = AsyncMock(side_effect=[self._make_og_resp(og_html), scraper_resp])
        msg = _make_message(self._MSG_URL)
        with caplog.at_level(logging.WARNING, logger="discord.cogs.social_preview.cog"):
            await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        assert any("login wall" in r.message or "SESSION_ID" in r.message for r in caplog.records)
        assert not any("empty result" in r.message for r in caplog.records)
