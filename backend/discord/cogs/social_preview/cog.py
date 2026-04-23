"""Social media link preview cog.

Listens for social media URLs that Discord cannot embed natively and
replies with a unified rich embed preview.

Supported platforms
-------------------
- Instagram  — Self-hosted InstaFix proxy (github.com/Wikidepia/InstaFix)
- Threads    — Discordbot UA OG scraping; oEmbed as forward-compat fallback
               Post captions require the Scrapling sidecar (browser automation)
- Bilibili   — Public API (no key required); videos, spaces, and live rooms
- TikTok     — oEmbed API (public, no key required)
- Twitch     — Helix API (requires TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET)

Excluded platforms
------------------
- X / Twitter  — Discord native embed is sufficient
- YouTube      — Discord native embed is sufficient
- Facebook     — Login wall, no viable server-side solution
- 小紅書        — Requires maintained cookie session (7-day expiry)
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from html.parser import HTMLParser
from urllib.parse import quote_plus, unquote

import discord
import httpx
from discord.ext import commands

from core import DATA_DIR, EmbedFactory, UserBoundView, get_settings, load_json

from ._embeds import (
    build_bilibili_embed,
    build_bilibili_live_embed,
    build_bilibili_space_embed,
    build_instagram_embed,
    build_instagram_profile_embed,
    build_threads_embed,
    build_threads_profile_embed,
    build_tiktok_embed,
    build_twitch_channel_embed,
    build_twitch_clip_embed,
)
from .constants import (
    BILIBILI_API,
    BILIBILI_CARD_API,
    BILIBILI_LIVE_API,
    BILIBILI_LIVE_RE,
    BILIBILI_RE,
    BILIBILI_SPACE_RE,
    DISMISS_TIMEOUT,
    HTTP_TIMEOUT,
    INSTAGRAM_APP_ID,
    INSTAGRAM_PROFILE_API,
    INSTAGRAM_PROFILE_RE,
    INSTAGRAM_PROXY_URL,
    INSTAGRAM_RE,
    THREADS_OEMBED_API,
    THREADS_PROFILE_RE,
    THREADS_RE,
    TIKTOK_OEMBED_API,
    TIKTOK_RE,
    TWITCH_CHANNEL_RE,
    TWITCH_CLIP_RE,
    TWITCH_HELIX_CLIPS_API,
    TWITCH_HELIX_GAMES_API,
    TWITCH_HELIX_STREAMS_API,
    TWITCH_HELIX_USERS_API,
    TWITCH_HELIX_USERS_LOGIN_API,
    TWITCH_TOKEN_URL,
    VIDEO_MAX_BYTES,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BILIBILI_BV_RE = re.compile(r"BV[A-Za-z0-9]+")
_TWITCH_THUMB_RE = re.compile(r"-preview-\d+x\d+\.jpg$", re.IGNORECASE)


async def _anone() -> None:
    return None


async def _anone_pair() -> tuple[None, None]:
    return None, None


def _twitch_clip_mp4_url(thumbnail_url: str) -> str | None:
    """Derive the direct MP4 URL from a Twitch clip thumbnail URL.

    Twitch CDN pattern: <base>-preview-<W>x<H>.jpg → <base>.mp4
    Returns None if the thumbnail URL doesn't match the expected pattern.
    """
    if not thumbnail_url or not _TWITCH_THUMB_RE.search(thumbnail_url):
        return None
    return _TWITCH_THUMB_RE.sub(".mp4", thumbnail_url)


class _BasePreviewView(UserBoundView):
    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass


class _CarouselView(_BasePreviewView):
    """Base class for ◀ 1/N ▶ carousel navigation views."""

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
    ) -> None:
        super().__init__(user_id, timeout=DISMISS_TIMEOUT)
        self._items = items
        self.current = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self._items) - 1
        self.page_btn.label = f"{self.current + 1}/{len(self._items)}"

    def _build_embed(self) -> discord.Embed:
        raise NotImplementedError

    async def _navigate(self, interaction: discord.Interaction) -> None:
        # Guard against Discord race condition where a disabled button fires late.
        if not (0 <= self.current < len(self._items)):
            await interaction.response.defer()
            return
        await interaction.response.edit_message(
            embed=self._build_embed(), view=self, attachments=[]
        )

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.current = max(0, self.current - 1)
        self._sync_buttons()
        await self._navigate(interaction)

    @discord.ui.button(label="…", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.current = min(len(self._items) - 1, self.current + 1)
        self._sync_buttons()
        await self._navigate(interaction)

    async def on_timeout(self) -> None:
        if self.message:
            try:
                self.current = 0
                await self.message.edit(embed=self._build_embed(), view=None, attachments=[])
            except (discord.NotFound, discord.HTTPException):
                pass


class _InstagramCarouselView(_CarouselView):
    """◀ 1/N ▶ photo navigation for Instagram carousel posts."""

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
        factory: EmbedFactory,
        og_meta: dict[str, str],
        post_url: str,
    ) -> None:
        super().__init__(user_id, items)
        self._factory = factory
        self._og_meta = og_meta
        self._post_url = post_url

    def _build_embed(self) -> discord.Embed:
        image_cdn, _ = self._items[self.current]
        meta = {**self._og_meta, "image": image_cdn} if image_cdn else self._og_meta
        return build_instagram_embed(self._factory, meta, self._post_url)


class _ThreadsCarouselView(_CarouselView):
    """◀ 1/N ▶ navigation for Threads image carousel posts.

    Paginates image slots only. Videos are sent once as a bundled reply at
    creation time and are never deleted by this view.
    """

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
        factory: EmbedFactory,
        data: dict,
        post_url: str,
    ) -> None:
        super().__init__(user_id, items)
        self._factory = factory
        self._data = data
        self._post_url = post_url

    def _build_embed(self) -> discord.Embed:
        image_url, _ = self._items[self.current]
        return build_threads_embed(
            self._factory,
            {**self._data, "image_urls": [image_url] if image_url else [], "video_urls": []},
            self._post_url,
        )


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
        self._twitch_token: str | None = None
        self._twitch_token_exp: float = 0.0
        self._twitch_token_lock = asyncio.Lock()

    async def cog_unload(self) -> None:
        await self._http.aclose()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        content = message.content

        for pattern, handler in (
            (INSTAGRAM_RE, self._handle_instagram),
            (INSTAGRAM_PROFILE_RE, self._handle_instagram_profile),
            (THREADS_RE, self._handle_threads),
            (THREADS_PROFILE_RE, self._handle_threads_profile),
            (BILIBILI_LIVE_RE, self._handle_bilibili_live),
            (BILIBILI_SPACE_RE, self._handle_bilibili_space),
            (BILIBILI_RE, self._handle_bilibili),
            (TIKTOK_RE, self._handle_tiktok),
            (TWITCH_CLIP_RE, self._handle_twitch_clip),
            (TWITCH_CHANNEL_RE, self._handle_twitch_channel),
        ):
            m = pattern.search(content)
            if m:
                try:
                    await handler(message, m)
                except Exception:
                    LOGGER.exception("Unhandled error in %s handler", handler.__name__)
                return

    async def _handle_instagram(self, message: discord.Message, match: re.Match[str]) -> None:
        path, shortcode = match.group(1), match.group(2)
        original_url = f"https://www.instagram.com/{path}/{shortcode}/"

        proxy_url = INSTAGRAM_PROXY_URL.format(
            host=get_settings().instafix_host, path=path, shortcode=shortcode
        )
        og = await self._fetch_og(proxy_url, bot_ua=True)
        if not og:
            # InstaFix may have cached a failed scrape — retry once with a cache-bust param.
            og = await self._fetch_og(f"{proxy_url}?_={shortcode[:6]}", bot_ua=True)
        if not og:
            LOGGER.debug("Instagram: no OG data from InstaFix for %s", shortcode)
            return

        LOGGER.debug("Instagram OG for %s → %r", shortcode, og)
        img_path = og.get("image", "")
        og_meta = {k: v for k, v in og.items() if k != "image"}

        # New InstaFix format (twitter:title = "@handle"): fire a concurrent profile API call
        # to enrich the title with the display name before entering each branch.
        raw_title = og_meta.get("title", "")
        _handle_clean: str | None = None
        if raw_title and " on Instagram" not in raw_title:
            candidate = raw_title.lstrip("@")
            if candidate and re.fullmatch(r"[\w.]{1,30}", candidate):
                _handle_clean = candidate
        _profile_task = (
            asyncio.create_task(self._fetch_instagram_profile(_handle_clean))
            if _handle_clean and get_settings().instagram_session_id
            else None
        )

        async def _apply_display_name(meta: dict[str, str]) -> dict[str, str]:
            if not _profile_task:
                return meta
            user = await _profile_task
            if user and (full_name := user.get("full_name")):
                return {**meta, "title": f"{full_name} (@{_handle_clean})"}
            return meta

        try:
            if img_path.startswith("/grid/"):
                items, fallback_title = await self._probe_instagram_items(shortcode)
                if not items:
                    return
                og_meta = await _apply_display_name(og_meta)
                if not og_meta.get("title") and fallback_title:
                    og_meta = {**og_meta, "title": fallback_title}

                # Photos go into the carousel; videos are sent as a bundled reply.
                photo_items: list[tuple[str | None, str | None]] = [
                    (img, None) for img, vid in items if vid is None and img is not None
                ]
                video_cdns: list[str] = [vid for _, vid in items if vid is not None]

                dl_results = await asyncio.gather(
                    *(self._download_cdn_bytes(cdn) for cdn in video_cdns)
                )
                vid_bytes_list: list[bytes] = [b for b in dl_results if b is not None]

                first_image = photo_items[0][0] if photo_items else None
                embed = build_instagram_embed(
                    self._embed,
                    {**og_meta, "image": first_image} if first_image else og_meta,
                    original_url,
                )

                if len(photo_items) > 1:
                    carousel_view = _InstagramCarouselView(
                        message.author.id,
                        photo_items,
                        self._embed,
                        og_meta,
                        original_url,
                    )
                    sent = await self._send_preview(message, embed, view=carousel_view)
                else:
                    sent = await self._send_preview(message, embed)

                if sent:
                    await self._send_file_bundle(message, vid_bytes_list, sent, filename="reel.mp4")

            elif img_path.startswith("/images/"):
                cdn, video_cdn, og_meta = await asyncio.gather(
                    self._resolve_instafix_redirect(img_path),
                    self._resolve_instafix_redirect(f"/videos/{shortcode}/1", require_mp4=True),
                    _apply_display_name(og_meta),
                )
                if not cdn:
                    return
                embed = build_instagram_embed(self._embed, {**og_meta, "image": cdn}, original_url)
                vid_bytes = await self._download_cdn_bytes(video_cdn) if video_cdn else None
                sent = await self._send_preview(message, embed)
                if sent and vid_bytes:
                    await self._send_file_bundle(message, [vid_bytes], sent, filename="reel.mp4")

            elif not img_path:
                # Reel with no thumbnail — video only.
                video_path = og_meta.get("video", "")
                if not video_path.startswith("/videos/"):
                    return
                og_meta = await _apply_display_name(og_meta)
                embed = build_instagram_embed(self._embed, og_meta, original_url)
                cdn_url = await self._resolve_instafix_redirect(video_path, require_mp4=True)
                vid_bytes = await self._download_cdn_bytes(cdn_url) if cdn_url else None
                sent = await self._send_preview(message, embed)
                if sent and vid_bytes:
                    await self._send_file_bundle(message, [vid_bytes], sent, filename="reel.mp4")

            else:
                LOGGER.debug("Instagram: unexpected image path %r for %s", img_path, shortcode)
        finally:
            if _profile_task is not None and not _profile_task.done():
                _profile_task.cancel()

    async def _handle_instagram_profile(
        self, message: discord.Message, match: re.Match[str]
    ) -> None:
        if not get_settings().instagram_session_id:
            return
        username = match.group(1)
        profile_url = f"https://www.instagram.com/{username}/"

        user = await self._fetch_instagram_profile(username)

        if user:
            og: dict[str, str] = {
                "title": user.get("full_name") or f"@{username}",
                "description": user.get("biography") or "",
                "image": (user.get("profile_pic_url_hd") or user.get("profile_pic_url") or ""),
            }
            posts = (user.get("edge_owner_to_timeline_media") or {}).get("count")
            followers = (user.get("edge_followed_by") or {}).get("count")
            following = (user.get("edge_follow") or {}).get("count")
        else:
            og = {}
            posts = followers = following = None
            LOGGER.debug("Instagram profile: API failed for @%s, sending minimal embed", username)

        embed = build_instagram_profile_embed(
            self._embed,
            og,
            username,
            profile_url,
            posts=posts,
            followers=followers,
            following=following,
        )
        await self._send_preview(message, embed)

    async def _fetch_instagram_profile(self, username: str) -> dict | None:
        """Fetch public profile data from Instagram's internal web API.

        Unauthenticated requests 429 quickly; set INSTAGRAM_SESSION_ID in .env.
        Returns data.user dict, or None on any failure.
        """
        url = INSTAGRAM_PROFILE_API.format(username=username)
        headers: dict[str, str] = {
            "X-IG-App-ID": INSTAGRAM_APP_ID,
            "Referer": "https://www.instagram.com/",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.instagram.com",
        }
        if session_id := get_settings().instagram_session_id:
            decoded = unquote(session_id)
            ds_user_id = decoded.split(":")[0]
            cookie = f"sessionid={decoded}"
            if ds_user_id.isdigit():
                cookie += f"; ds_user_id={ds_user_id}"
            headers["Cookie"] = cookie
        try:
            resp = await self._http.get(url, headers=headers)
            resp.raise_for_status()
            return (resp.json().get("data") or {}).get("user")
        except Exception as exc:
            LOGGER.debug("Instagram profile API failed for @%s: %s", username, exc)
            return None

    async def _handle_threads(self, message: discord.Message, match: re.Match[str]) -> None:
        post_url = match.group(0)

        data = await self._fetch_og(post_url, bot_ua=True, follow_redirects=True)
        LOGGER.debug("Threads bot-UA OG: %r", data)

        # oEmbed currently returns a login-wall; kept as forward-compatibility fallback.
        if not data:
            data = await self._fetch_threads_oembed(post_url)
            LOGGER.debug("Threads oEmbed: %r", data)

        if not data:
            LOGGER.debug("Threads: all fetch paths failed for %s", post_url)
            return

        if scrapling_data := await self._fetch_scrapling("threads", post_url):
            data = {**data, **scrapling_data}

        raw_media: list[dict] = data.get("media_items") or []  # type: ignore[assignment]
        all_items: list[tuple[str | None, str | None]]
        if raw_media:
            all_items = [
                (None, m["url"]) if m["type"] == "video" else (m["url"], None)  # type: ignore[index]
                for m in raw_media
            ]
        else:
            image_urls: list[str] = data.get("image_urls") or []  # type: ignore[assignment]
            video_urls_og: list[str] = data.get("video_urls") or []  # type: ignore[assignment]
            all_items = [(url, None) for url in image_urls] + [(None, url) for url in video_urls_og]  # type: ignore[list-item]

        image_items: list[tuple[str | None, str | None]] = [
            (img, None) for img, vid in all_items if img is not None
        ]
        video_url_list = [vid for img, vid in all_items if vid is not None]

        dl_results = await asyncio.gather(
            *(self._download_cdn_bytes(url) for url in video_url_list)
        )
        video_bytes_list: list[bytes] = [b for b in dl_results if b is not None]

        if len(image_items) >= 2:
            carousel_view = _ThreadsCarouselView(
                message.author.id, image_items, self._embed, data, post_url
            )
            sent = await self._send_preview(
                message, carousel_view._build_embed(), view=carousel_view
            )
            if sent:
                await self._send_file_bundle(message, video_bytes_list, sent)
        elif image_items:
            img_url = image_items[0][0]
            embed = build_threads_embed(
                self._embed, {**data, "image_urls": [img_url], "video_urls": []}, post_url
            )
            sent = await self._send_preview(message, embed)
            if sent:
                await self._send_file_bundle(message, video_bytes_list, sent)
        else:
            embed_data = (
                {**data, "image_urls": [], "video_urls": [], "image": ""}
                if video_bytes_list
                else data
            )
            sent = await self._send_preview(
                message, build_threads_embed(self._embed, embed_data, post_url)
            )
            if sent:
                await self._send_file_bundle(message, video_bytes_list, sent)

    async def _handle_threads_profile(self, message: discord.Message, match: re.Match[str]) -> None:
        handle = match.group(1)
        profile_url = f"https://www.threads.com/@{handle}"
        og, scrapling_data = await asyncio.gather(
            self._fetch_og(profile_url, bot_ua=True, follow_redirects=True),
            self._fetch_scrapling("threads/profile", profile_url),
        )
        if not og:
            LOGGER.debug("Threads profile: no OG data for @%s", handle)
            return
        embed = build_threads_profile_embed(self._embed, {**og, **scrapling_data}, profile_url)
        await self._send_preview(message, embed)

    async def _fetch_scrapling(self, endpoint: str, url: str) -> dict:
        """Call the Scrapling sidecar at *endpoint* for *url*.

        Timeout is 35 s — sidecar may spend up to 30 s on navigation + hydration.
        Returns a dict of non-empty fields, or {} when the host is unconfigured or on error.
        """
        host = get_settings().scrapling_host
        if not host:
            return {}
        api_url = f"http://{host}/{endpoint}?url={quote_plus(url)}"
        try:
            resp = await self._http.get(api_url, timeout=35.0)
            resp.raise_for_status()
            body: dict = resp.json()
            LOGGER.info("Scrapling %s: %s", endpoint, {k: v for k, v in body.items() if v})
            return {k: v for k, v in body.items() if v}
        except Exception as exc:
            LOGGER.warning("Scrapling sidecar failed for %s: %s", url, exc)
            return {}

    async def _fetch_threads_oembed(self, post_url: str) -> dict | None:
        """Fetch Threads oEmbed metadata for *post_url*.

        The unauthenticated threads.com oEmbed endpoint currently returns an HTML
        login-wall regardless of Accept headers; kept as forward-compatibility fallback.

        Returns the parsed JSON dict if ``author_name`` is present, else None.
        """
        api_url = THREADS_OEMBED_API.format(url=quote_plus(post_url))
        try:
            resp = await self._http.get(
                api_url,
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            if "json" not in resp.headers.get("content-type", ""):
                LOGGER.debug(
                    "Threads oEmbed non-JSON response: ct=%r body=%r for %s",
                    resp.headers.get("content-type", ""),
                    resp.text[:120],
                    post_url,
                )
                return None
            data = resp.json()
            return data if data.get("author_name") else None
        except Exception as exc:
            LOGGER.debug("Threads oEmbed failed for %s: %s", post_url, exc)
            return None

    async def _handle_bilibili(self, message: discord.Message, match: re.Match[str]) -> None:
        bvid = match.group(1)

        if not bvid:
            short_url = match.group(0)
            try:
                resp = await self._http.head(short_url, follow_redirects=True)
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

    async def _handle_bilibili_space(self, message: discord.Message, match: re.Match[str]) -> None:
        mid = match.group(1)
        space_url = f"https://space.bilibili.com/{mid}"
        try:
            resp = await self._http.get(
                BILIBILI_CARD_API.format(mid=mid),
                headers={
                    "Referer": "https://www.bilibili.com",
                    "User-Agent": _UA,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            LOGGER.debug("Bilibili card API failed for mid=%s: %s", mid, exc)
            return

        if body.get("code") != 0 or not body.get("data"):
            return

        await self._send_preview(
            message, build_bilibili_space_embed(self._embed, body["data"], space_url)
        )

    async def _handle_bilibili_live(self, message: discord.Message, match: re.Match[str]) -> None:
        room_id = match.group(1)
        room_url = f"https://live.bilibili.com/{room_id}"
        try:
            resp = await self._http.get(
                BILIBILI_LIVE_API.format(room_id=room_id),
                headers={"Referer": "https://live.bilibili.com"},
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            LOGGER.debug("Bilibili live API failed for room_id=%s: %s", room_id, exc)
            return

        if body.get("code") != 0 or not body.get("data"):
            return

        room = body["data"]
        uid = room.get("uid")

        card_data: dict | None = None
        if uid:
            try:
                card_resp = await self._http.get(
                    BILIBILI_CARD_API.format(mid=uid),
                    headers={"Referer": "https://www.bilibili.com"},
                )
                card_resp.raise_for_status()
                card_body = card_resp.json()
                if card_body.get("code") == 0 and card_body.get("data"):
                    card_data = card_body["data"]
            except Exception as exc:
                LOGGER.debug("Bilibili card API failed for uid=%s: %s", uid, exc)

        await self._send_preview(
            message, build_bilibili_live_embed(self._embed, room, card_data, room_url)
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

    async def _get_twitch_token(self) -> str | None:
        """Return a cached app-access token, refreshing if expired or missing."""
        if self._twitch_token and time.monotonic() < self._twitch_token_exp:
            return self._twitch_token
        async with self._twitch_token_lock:
            if self._twitch_token and time.monotonic() < self._twitch_token_exp:
                return self._twitch_token
            s = get_settings()
            if not s.twitch_client_id or not s.twitch_client_secret:
                return None
            try:
                resp = await self._http.post(
                    TWITCH_TOKEN_URL,
                    data={
                        "client_id": s.twitch_client_id,
                        "client_secret": s.twitch_client_secret,
                        "grant_type": "client_credentials",
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                self._twitch_token = body["access_token"]
                # Expire 60 s early to avoid using a token right at its boundary.
                self._twitch_token_exp = time.monotonic() + body.get("expires_in", 3600) - 60
                return self._twitch_token
            except Exception as exc:
                LOGGER.debug("Twitch token fetch failed: %s", exc)
                return None

    async def _twitch_helix_get(self, url: str, token: str) -> list[dict]:
        """GET a Twitch Helix endpoint and return the data list, or [] on failure."""
        s = get_settings()
        try:
            resp = await self._http.get(
                url,
                headers={"Client-ID": s.twitch_client_id, "Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])  # type: ignore[no-any-return]
        except Exception as exc:
            LOGGER.debug("Twitch Helix request failed for %s: %s", url, exc)
            return []

    async def _fetch_twitch_user_info(
        self, user_id: str, token: str
    ) -> tuple[str | None, str | None]:
        data = await self._twitch_helix_get(TWITCH_HELIX_USERS_API.format(user_id=user_id), token)
        if not data:
            return None, None
        u = data[0]
        return u.get("profile_image_url"), u.get("login")

    async def _fetch_twitch_game_name(self, game_id: str, token: str) -> str | None:
        data = await self._twitch_helix_get(TWITCH_HELIX_GAMES_API.format(game_id=game_id), token)
        return data[0].get("name") if data else None

    async def _handle_twitch_clip(self, message: discord.Message, match: re.Match[str]) -> None:
        clip_id = match.group(1) or match.group(2)
        token = await self._get_twitch_token()
        if not token:
            return

        clips = await self._twitch_helix_get(TWITCH_HELIX_CLIPS_API.format(clip_id=clip_id), token)
        if not clips:
            return

        clip = clips[0]
        clip_url = f"https://clips.twitch.tv/{clip_id}"
        broadcaster_id = clip.get("broadcaster_id", "")
        game_id = clip.get("game_id", "")
        mp4_url = _twitch_clip_mp4_url(clip.get("thumbnail_url", ""))

        user_info, game_name, vid_bytes = await asyncio.gather(
            self._fetch_twitch_user_info(broadcaster_id, token)
            if broadcaster_id
            else _anone_pair(),
            self._fetch_twitch_game_name(game_id, token) if game_id else _anone(),
            self._download_cdn_bytes(mp4_url) if mp4_url else _anone(),
        )

        broadcaster_avatar, broadcaster_login = user_info
        broadcaster_url = f"https://twitch.tv/{broadcaster_login}" if broadcaster_login else None

        embed = build_twitch_clip_embed(
            self._embed,
            clip,
            clip_url,
            broadcaster_avatar=broadcaster_avatar,
            broadcaster_url=broadcaster_url,
            game_name=game_name,
        )
        sent = await self._send_preview(message, embed)
        if sent and vid_bytes:
            await self._send_file_bundle(message, [vid_bytes], sent, filename="clip.mp4")

    async def _handle_twitch_channel(self, message: discord.Message, match: re.Match[str]) -> None:
        login = match.group(1).lower()
        channel_url = f"https://twitch.tv/{login}"
        token = await self._get_twitch_token()
        if not token:
            return

        streams, users = await asyncio.gather(
            self._twitch_helix_get(TWITCH_HELIX_STREAMS_API.format(login=login), token),
            self._twitch_helix_get(TWITCH_HELIX_USERS_LOGIN_API.format(login=login), token),
        )

        if not users:
            return

        embed = build_twitch_channel_embed(
            self._embed,
            streams[0] if streams else None,
            users[0],
            channel_url,
        )
        await self._send_preview(message, embed)

    async def _send_preview(
        self,
        message: discord.Message,
        embed: discord.Embed,
        *,
        view: _BasePreviewView | None = None,
    ) -> discord.Message | None:
        kwargs: dict = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        try:
            sent = await message.channel.send(**kwargs)
        except (discord.Forbidden, discord.HTTPException):
            return None
        if view is not None:
            view.message = sent

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        return sent

    async def _send_file_bundle(
        self,
        message: discord.Message,
        bytes_list: list[bytes],
        ref: discord.Message,
        *,
        filename: str = "video.mp4",
    ) -> None:
        """Send pre-downloaded video bytes as a bundled reply to *ref*."""
        if not bytes_list:
            return
        files = [discord.File(io.BytesIO(b), filename=filename) for b in bytes_list]
        try:
            await message.channel.send(files=files, reference=ref)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _resolve_instafix_redirect(
        self, path: str, *, require_mp4: bool = False
    ) -> str | None:
        """Follow a single InstaFix 302 and return the CDN URL.

        require_mp4=True discards non-MP4 redirects (InstaFix can return .jpg
        via the /videos/ endpoint for photo carousel items).
        """
        if not path.startswith("/"):
            LOGGER.warning("Unexpected InstaFix path (not relative): %r", path)
            return None
        url = f"http://{get_settings().instafix_host}{path}"
        try:
            resp = await self._http.get(
                url,
                headers={"User-Agent": "Discordbot/2.0"},
                follow_redirects=False,
            )
            if not resp.is_redirect:
                return None
            cdn_url = str(resp.headers["location"])
            if require_mp4 and ".mp4" not in cdn_url.split("?")[0]:
                return None
            return cdn_url
        except Exception as exc:
            LOGGER.debug("InstaFix redirect failed for %s: %s", path, exc)
            return None

    async def _download_cdn_bytes(self, cdn_url: str) -> bytes | None:
        try:
            chunks: list[bytes] = []
            total = 0
            async with self._http.stream("GET", cdn_url, follow_redirects=True) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(65536):
                    total += len(chunk)
                    if total > VIDEO_MAX_BYTES:
                        LOGGER.debug(
                            "Video exceeds %d MB limit, skipping",
                            VIDEO_MAX_BYTES // 1024 // 1024,
                        )
                        await resp.aclose()
                        return None
                    chunks.append(chunk)
            return b"".join(chunks)
        except Exception as exc:
            LOGGER.debug("CDN download failed for %s: %s", cdn_url, exc)
            return None

    async def _probe_instagram_items(
        self, shortcode: str
    ) -> tuple[list[tuple[str | None, str | None]], str | None]:
        """Probe carousel items concurrently (1–4, extending to 10 if index 4 has media).

        Returns (items, fallback_title); each item is (image_cdn_url, video_cdn_url).
        fallback_title is needed because the /grid/ OG response often omits og:title.
        """

        async def _fetch_one(
            i: int,
        ) -> tuple[str | None, str | None, str | None]:
            # image_cdn, video_cdn, title
            url = f"http://{get_settings().instafix_host}/p/{shortcode}/?img_index={i}"
            og = await self._fetch_og(url, bot_ua=True)

            og_image = og.get("image", "") if og else ""

            # Determine redirect path for the image (None → direct URL or unknown)
            if og_image.startswith("/images/"):
                image_redirect = og_image
            elif og_image.startswith("/videos/"):
                # InstaFix uses /videos/ as og:image for video items; swap prefix for JPEG.
                image_redirect = og_image.replace("/videos/", "/images/", 1)
            else:
                image_redirect = None

            image_cdn_resolved = (
                await self._resolve_instafix_redirect(image_redirect) if image_redirect else None
            )
            video_cdn = await self._resolve_instafix_redirect(
                f"/videos/{shortcode}/{i}", require_mp4=True
            )
            image_cdn: str | None = image_cdn_resolved or (
                og_image if og_image.startswith(("http://", "https://")) else None
            )

            LOGGER.debug(
                "Instagram img_index=%d for %s → og_image=%r image_cdn=%s video_cdn=%s",
                i,
                shortcode,
                og_image,
                bool(image_cdn),
                bool(video_cdn),
            )

            # Video items sometimes have no og:image — probe /images/ as fallback.
            if image_cdn is None and video_cdn is not None:
                candidate = await self._resolve_instafix_redirect(f"/images/{shortcode}/{i}")
                # InstaFix may redirect /images/ to MP4 for video items; discard those.
                if candidate and ".mp4" in candidate.split("?")[0]:
                    LOGGER.debug("Instagram img_index=%d fallback returned MP4 URL, discarding", i)
                    candidate = None
                image_cdn = candidate
                LOGGER.debug(
                    "Instagram img_index=%d fallback image_cdn=%r",
                    i,
                    image_cdn[:80] if image_cdn else None,
                )

            title = og.get("title") if og else None
            return image_cdn, video_cdn, title

        results = list(await asyncio.gather(*(_fetch_one(i) for i in range(1, 5))))
        # Only probe 5–10 if index 4 returned any media
        if results[-1][0] is not None or results[-1][1] is not None:
            results += list(await asyncio.gather(*(_fetch_one(i) for i in range(5, 11))))

        items = [(img, vid) for img, vid, _ in results if img is not None or vid is not None]
        fallback_title: str | None = next(
            (title for _, _, title in results if title is not None), None
        )
        return items, fallback_title

    async def _fetch_og(
        self,
        url: str,
        *,
        bot_ua: bool = False,
        follow_redirects: bool = False,
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
