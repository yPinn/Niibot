"""Social media link preview cog.

Listens for social media URLs that Discord cannot embed natively and
replies with a unified rich embed preview.

Supported platforms
-------------------
- Instagram  — Self-hosted InstaFix proxy (github.com/Wikidepia/InstaFix)
- Threads    — Direct OG scraping (currently broken: Meta login wall)
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

import asyncio
import logging
import re
from html.parser import HTMLParser
from urllib.parse import quote_plus

import discord
import httpx
from discord.ext import commands

from core import DATA_DIR, EmbedFactory, UserBoundView, load_json

from ._embeds import (
    build_bilibili_embed,
    build_instagram_embed,
    build_threads_embed,
    build_tiktok_embed,
)
from .constants import (
    BILIBILI_API,
    BILIBILI_RE,
    DISMISS_TIMEOUT,
    HTTP_TIMEOUT,
    INSTAFIX_HOST,
    INSTAGRAM_PROXY_URL,
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


class _BasePreviewView(UserBoundView):
    """Shared timeout behaviour: remove buttons without modifying the embed."""

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass


class _DismissView(_BasePreviewView):
    """A single ✕ button that lets the original poster (or a moderator)
    delete the bot's preview reply.  Removes itself after *timeout* seconds.
    """

    def __init__(self, user_id: int) -> None:
        super().__init__(user_id, timeout=DISMISS_TIMEOUT)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        if (
            isinstance(interaction.channel, discord.TextChannel)
            and isinstance(interaction.user, discord.Member)
            and interaction.channel.permissions_for(interaction.user).manage_messages
        ):
            return True
        await interaction.response.send_message("只有原發文者可以關閉預覽。", ephemeral=True)
        return False

    @discord.ui.button(label="✕", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.message.delete()  # type: ignore[union-attr]


class _InstagramCarouselView(_BasePreviewView):
    """◀ 1/N ▶ navigation for multi-image Instagram posts."""

    def __init__(
        self,
        user_id: int,
        cdn_urls: list[str],
        factory: EmbedFactory,
        og_meta: dict[str, str],
        post_url: str,
    ) -> None:
        super().__init__(user_id, timeout=DISMISS_TIMEOUT)
        self.cdn_urls = cdn_urls
        self._factory = factory
        self._og_meta = og_meta
        self._post_url = post_url
        self.current = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self.cdn_urls) - 1
        self.page_btn.label = f"{self.current + 1}/{len(self.cdn_urls)}"

    def _build_embed(self) -> discord.Embed:
        embed = build_instagram_embed(
            self._factory,
            {**self._og_meta, "image": self.cdn_urls[self.current]},
            self._post_url,
        )
        embed.set_footer(
            text=f"Niibot • {self.current + 1}/{len(self.cdn_urls)}",
            icon_url=embed.footer.icon_url,
        )
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.current -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="…", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.current += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


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
        elif prop == "twitter:title" and content:
            # InstaFix sets the username in twitter:title, not og:title
            self.og.setdefault("title", content)


def _parse_og(html: str) -> dict[str, str]:
    parser = _OGParser()
    parser.feed(html[:20_000])
    return parser.og


class SocialPreviewCog(commands.Cog, name="SocialPreview"):
    """Auto-embed previews for social media links Discord cannot embed."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": _UA},
        )

    async def cog_unload(self) -> None:
        await self._http.aclose()

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

    async def _handle_instagram(self, message: discord.Message, match: re.Match[str]) -> None:
        path, shortcode = match.group(1), match.group(2)
        original_url = f"https://www.instagram.com/{path}/{shortcode}/"

        # Reels/TV: InstaFix redirects to Instagram directly — skip the proxy hop.
        if path in ("reel", "tv"):
            og = await self._fetch_og(original_url, bot_ua=True, follow_redirects=True)
            if not og or not og.get("image", "").startswith("http"):
                LOGGER.debug("Instagram reel: no OG data for %s", shortcode)
                return
            await self._send_preview(message, build_instagram_embed(self._embed, og, original_url))
            return

        proxy_url = INSTAGRAM_PROXY_URL.format(host=INSTAFIX_HOST, path=path, shortcode=shortcode)
        og = await self._fetch_og(proxy_url, bot_ua=True)
        if not og:
            LOGGER.debug("Instagram: no OG data from InstaFix for %s", shortcode)
            return

        LOGGER.debug("Instagram OG for %s → %r", shortcode, og)
        img_path = og.get("image", "")
        og_meta = {k: v for k, v in og.items() if k != "image"}

        if img_path.startswith("/grid/"):
            cdn_urls, fallback_title = await self._probe_instagram_images(shortcode)
            if not cdn_urls:
                return
            if not og_meta.get("title") and fallback_title:
                og_meta = {**og_meta, "title": fallback_title}
        elif img_path.startswith("/images/"):
            cdn = await self._resolve_instafix_image(img_path)
            cdn_urls = [cdn] if cdn else []
            if not cdn_urls:
                return
        else:
            return

        embed = build_instagram_embed(
            self._embed,
            {**og_meta, "image": cdn_urls[0]},
            original_url,
        )

        if len(cdn_urls) > 1:
            embed.set_footer(
                text=f"Niibot • 1/{len(cdn_urls)}",
                icon_url=embed.footer.icon_url,
            )
            view: discord.ui.View = _InstagramCarouselView(
                message.author.id,
                cdn_urls,
                self._embed,
                og_meta,
                original_url,
            )
        else:
            view = _DismissView(message.author.id)

        await self._send_preview(message, embed, view=view)

    async def _handle_threads(self, message: discord.Message, match: re.Match[str]) -> None:
        # TODO: Threads OG scraping is blocked by Meta's login wall.
        # Needs a dedicated solution (proxy or official API with user token).
        post_url = match.group(0)
        og = await self._fetch_og(post_url)
        if not og:
            return
        await self._send_preview(message, build_threads_embed(self._embed, og, post_url))

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

        await self._send_preview(
            message, build_bilibili_embed(self._embed, body["data"], video_url)
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

        await self._send_preview(message, build_tiktok_embed(self._embed, oembed, post_url))

    async def _send_preview(
        self,
        message: discord.Message,
        embed: discord.Embed,
        *,
        view: discord.ui.View | None = None,
    ) -> None:
        if view is None:
            view = _DismissView(message.author.id)
        sent = await message.channel.send(embed=embed, view=view)
        if hasattr(view, "message"):
            view.message = sent  # type: ignore[union-attr]

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    async def _resolve_instafix_image(self, img_path: str) -> str | None:
        """Follow InstaFix's 302 redirect to get the Instagram CDN URL without downloading the image."""
        img_url = f"http://{INSTAFIX_HOST}{img_path}"
        try:
            resp = await self._http.get(
                img_url,
                headers={"User-Agent": "Discordbot/2.0"},
                follow_redirects=False,
            )
            if resp.is_redirect:
                return str(resp.headers["location"])
            # Unexpected 200 — return None rather than using internal URL
            return None
        except Exception as exc:
            LOGGER.debug("Image resolve failed for %s: %s", img_path, exc)
            return None

    async def _probe_instagram_images(self, shortcode: str) -> tuple[list[str], str | None]:
        """Fetch carousel CDN URLs concurrently. Probes 1–4 first, extends to 10 only if needed.

        Returns (cdn_urls, fallback_title).
        fallback_title covers carousel posts where the /grid/ request omits og:title.
        """

        async def _fetch_one(i: int) -> tuple[str | None, str | None]:
            url = f"http://{INSTAFIX_HOST}/p/{shortcode}/?img_index={i}"
            og = await self._fetch_og(url, bot_ua=True)
            if not og or not og.get("image", "").startswith("/images/"):
                return None, None
            if i == 1:
                LOGGER.debug("Instagram img_index=1 OG for %s → %r", shortcode, og)
            cdn = await self._resolve_instafix_image(og["image"])
            return cdn, og.get("title")

        results = list(await asyncio.gather(*(_fetch_one(i) for i in range(1, 5))))
        # Only probe 5–10 if index 4 returned a result (carousel has >4 images)
        if results[-1][0] is not None:
            results += list(await asyncio.gather(*(_fetch_one(i) for i in range(5, 11))))

        cdn_urls: list[str] = []
        fallback_title: str | None = None
        for cdn, title in results:
            if cdn is None:
                break
            cdn_urls.append(cdn)
            if fallback_title is None:
                fallback_title = title
        return cdn_urls, fallback_title

    async def _fetch_og(
        self, url: str, *, bot_ua: bool = False, follow_redirects: bool = False
    ) -> dict[str, str] | None:
        """Fetch OG tags from *url*. Use *bot_ua=True* for InstaFix (redirects Chrome UAs)."""
        headers = {"User-Agent": "Discordbot/2.0"} if bot_ua else {}
        try:
            resp = await self._http.get(url, follow_redirects=follow_redirects, headers=headers)
            if not follow_redirects and resp.is_redirect:
                return None
            resp.raise_for_status()
            og = _parse_og(resp.text)
            return og if og else None
        except Exception as exc:
            LOGGER.debug("OG fetch failed for %s: %s", url, exc)
            return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialPreviewCog(bot))
