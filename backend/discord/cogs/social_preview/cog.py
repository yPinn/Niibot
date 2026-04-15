"""Social media link preview cog.

Listens for social media URLs that Discord cannot embed natively and
replies with a unified rich embed preview.

Supported platforms
-------------------
- Instagram  — InstaFix proxy (ddinstagram.com) → OG tags
- Threads    — Direct OG scraping (best available, intermittent)
- Bilibili   — Public API (no key required)
- TikTok     — oEmbed API (public, no key required)

Excluded platforms
------------------
- X / Twitter  — Discord native embed is sufficient
- YouTube      — Discord native embed is sufficient
- Facebook     — Login wall, no viable server-side solution
- 小紅書        — Requires maintained cookie session (7-day expiry)
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import quote_plus

import discord
import httpx
from discord.ext import commands

from ._embeds import (
    build_bilibili_embed,
    build_instagram_embed,
    build_threads_embed,
    build_tiktok_embed,
)
from .constants import (
    BILIBILI_API,
    BILIBILI_RE,
    DDINSTAGRAM_HOST,
    HTTP_TIMEOUT,
    INSTAGRAM_RE,
    THREADS_RE,
    TIKTOK_OEMBED_API,
    TIKTOK_RE,
)

LOGGER = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BILIBILI_BV_RE = re.compile(r"BV[A-Za-z0-9]+")


# ── Open Graph scraper ────────────────────────────────────────────────────────


class _OGParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        attr = dict(attrs)
        prop = attr.get("property") or attr.get("name") or ""
        content = attr.get("content") or ""
        if prop.startswith("og:") and content:
            self.og.setdefault(prop[3:], content)


def _parse_og(html: str) -> dict[str, str]:
    parser = _OGParser()
    parser.feed(html[:20_000])
    return parser.og


# ── Cog ───────────────────────────────────────────────────────────────────────


class SocialPreviewCog(commands.Cog, name="SocialPreview"):
    """Auto-embed previews for social media links Discord cannot embed."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        )

    async def cog_unload(self) -> None:
        await self._http.aclose()

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        content = message.content

        for pattern, handler in (
            (INSTAGRAM_RE, self._handle_instagram),
            (THREADS_RE, self._handle_threads),
            (BILIBILI_RE, self._handle_bilibili),
            (TIKTOK_RE, self._handle_tiktok),
        ):
            m = pattern.search(content)
            if m:
                await handler(message, m)
                return

    # ── Platform handlers ─────────────────────────────────────────────────────

    async def _handle_instagram(self, message: discord.Message, match: re.Match[str]) -> None:
        shortcode = match.group(1)
        # Use InstaFix proxy — returns static HTML with OG tags, no login needed.
        # Original URL is passed as the embed link so clicking opens Instagram.
        proxy_url = f"https://{DDINSTAGRAM_HOST}/p/{shortcode}/"
        original_url = f"https://www.instagram.com/p/{shortcode}/"

        og = await self._fetch_og(proxy_url)
        if not og:
            return
        await message.reply(
            embed=build_instagram_embed(og, original_url),
            mention_author=False,
        )

    async def _handle_threads(self, message: discord.Message, match: re.Match[str]) -> None:
        post_url = match.group(0)
        og = await self._fetch_og(post_url)
        if not og:
            return
        await message.reply(embed=build_threads_embed(og, post_url), mention_author=False)

    async def _handle_bilibili(self, message: discord.Message, match: re.Match[str]) -> None:
        bvid = match.group(1)

        if not bvid:
            short_url = match.group(0)
            try:
                resp = await self._http.head(short_url)
                bv_m = _BILIBILI_BV_RE.search(str(resp.url))
                if not bv_m:
                    return
                bvid = bv_m.group(0)
            except Exception as exc:
                LOGGER.debug("b23.tv resolve failed for %s: %s", short_url, exc)
                return

        video_url = f"https://www.bilibili.com/video/{bvid}"
        try:
            resp = await self._http.get(
                BILIBILI_API.format(bvid=bvid),
                headers={"Referer": "https://www.bilibili.com"},
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            LOGGER.debug("Bilibili API failed for %s: %s", bvid, exc)
            return

        if body.get("code") != 0 or not body.get("data"):
            return

        await message.reply(
            embed=build_bilibili_embed(body["data"], video_url),
            mention_author=False,
        )

    async def _handle_tiktok(self, message: discord.Message, match: re.Match[str]) -> None:
        post_url = match.group(0)
        api_url = TIKTOK_OEMBED_API.format(url=quote_plus(post_url))
        try:
            resp = await self._http.get(api_url)
            resp.raise_for_status()
            oembed = resp.json()
        except Exception as exc:
            LOGGER.debug("TikTok oEmbed failed for %s: %s", post_url, exc)
            return

        if not oembed.get("title") and not oembed.get("author_name"):
            return

        await message.reply(
            embed=build_tiktok_embed(oembed, post_url),
            mention_author=False,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _fetch_og(self, url: str) -> dict[str, str] | None:
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            og = _parse_og(resp.text)
            return og if og else None
        except Exception as exc:
            LOGGER.debug("OG fetch failed for %s: %s", url, exc)
            return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialPreviewCog(bot))
