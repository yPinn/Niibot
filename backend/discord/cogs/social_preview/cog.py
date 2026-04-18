"""Social media link preview cog.

Listens for social media URLs that Discord cannot embed natively and
replies with a unified rich embed preview.

Supported platforms
-------------------
- Instagram  — Self-hosted InstaFix proxy (github.com/Wikidepia/InstaFix)
- Threads    — Direct OG scraping (currently broken: Meta login wall)
- Bilibili   — Public API (no key required)
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
    build_bilibili_space_embed,
    build_instagram_embed,
    build_instagram_profile_embed,
    build_threads_embed,
    build_tiktok_embed,
    build_twitch_channel_embed,
    build_twitch_clip_embed,
)
from .constants import (
    BILIBILI_API,
    BILIBILI_CARD_API,
    BILIBILI_RE,
    BILIBILI_SPACE_RE,
    DISMISS_TIMEOUT,
    HTTP_TIMEOUT,
    INSTAFIX_HOST,
    INSTAGRAM_APP_ID,
    INSTAGRAM_PROFILE_API,
    INSTAGRAM_PROFILE_RE,
    INSTAGRAM_PROXY_URL,
    INSTAGRAM_RE,
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

LOGGER = logging.getLogger(__name__)

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


class _InstagramCarouselView(_BasePreviewView):
    """◀ 1/N ▶ navigation for mixed photo/video carousel posts.

    Videos are pre-downloaded at init so navigation is instant. Each video
    is sent as a separate follow-up message so the embed always appears above
    the video player (Discord limitation).
    """

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
        video_bytes: dict[int, bytes],
        factory: EmbedFactory,
        og_meta: dict[str, str],
        post_url: str,
    ) -> None:
        super().__init__(user_id, timeout=DISMISS_TIMEOUT)
        self._items = items
        self._video_bytes = video_bytes  # index → pre-downloaded MP4 bytes
        self._factory = factory
        self._og_meta = og_meta
        self._post_url = post_url
        self.current = 0
        self._video_message: discord.Message | None = None
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self._items) - 1
        self.page_btn.label = f"{self.current + 1}/{len(self._items)}"

    def _build_embed(self) -> discord.Embed:
        image_cdn, _ = self._items[self.current]
        meta = {**self._og_meta, "image": image_cdn} if image_cdn else self._og_meta
        return build_instagram_embed(self._factory, meta, self._post_url)

    async def _delete_video_message(self) -> None:
        if self._video_message:
            try:
                await self._video_message.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            self._video_message = None

    def _make_video_file(self) -> discord.File | None:
        data = self._video_bytes.get(self.current)
        return discord.File(io.BytesIO(data), filename="reel.mp4") if data else None

    async def _send_video_reply(self, file: discord.File) -> None:
        if not self.message:
            return
        try:
            self._video_message = await self.message.channel.send(  # type: ignore[union-attr]
                file=file, reference=self.message
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _navigate(self, interaction: discord.Interaction) -> None:
        # Guard against Discord race condition where a disabled button fires late.
        if not (0 <= self.current < len(self._items)):
            await interaction.response.defer()
            return

        embed = self._build_embed()
        file = self._make_video_file()

        await self._delete_video_message()
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])

        if file:
            await self._send_video_reply(file)

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
        await self._delete_video_message()
        if self.message:
            try:
                self.current = 0
                await self.message.edit(embed=self._build_embed(), view=None, attachments=[])
            except (discord.NotFound, discord.HTTPException):
                pass


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

        proxy_url = INSTAGRAM_PROXY_URL.format(host=INSTAFIX_HOST, path=path, shortcode=shortcode)
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

        if img_path.startswith("/grid/"):
            items, fallback_title = await self._probe_instagram_items(shortcode)
            if not items:
                return
            if not og_meta.get("title") and fallback_title:
                og_meta = {**og_meta, "title": fallback_title}

            # Pre-download all videos concurrently so navigation is instant.
            async def _dl(i: int, cdn: str) -> tuple[int, bytes | None]:
                f = await self._download_cdn_video(cdn)
                if f is None:
                    return i, None
                f.fp.seek(0)
                return i, f.fp.read()

            dl_results = await asyncio.gather(
                *(_dl(i, vid) for i, (_, vid) in enumerate(items) if vid is not None)
            )
            video_bytes: dict[int, bytes] = {i: data for i, data in dl_results if data is not None}

            first_image, _ = items[0]
            embed = build_instagram_embed(
                self._embed,
                {**og_meta, "image": first_image} if first_image else og_meta,
                original_url,
            )
            first_data = video_bytes.get(0)
            first_file = (
                discord.File(io.BytesIO(first_data), filename="reel.mp4") if first_data else None
            )

            if len(items) > 1:
                carousel_view = _InstagramCarouselView(
                    message.author.id,
                    items,
                    video_bytes,
                    self._embed,
                    og_meta,
                    original_url,
                )
                await self._send_preview(message, embed, view=carousel_view)
                if first_file:
                    await carousel_view._send_video_reply(first_file)
            else:
                await self._send_preview(message, embed, file=first_file)

        elif img_path.startswith("/images/"):
            cdn, video_cdn = await asyncio.gather(
                self._resolve_instafix_redirect(img_path),
                self._resolve_instafix_redirect(f"/videos/{shortcode}/1", require_mp4=True),
            )
            if not cdn:
                return
            embed = build_instagram_embed(self._embed, {**og_meta, "image": cdn}, original_url)
            file = await self._download_cdn_video(video_cdn) if video_cdn else None
            await self._send_preview(message, embed, file=file)

        elif not img_path:
            # Reel with no thumbnail — video only.
            video_path = og_meta.get("video", "")
            if not video_path.startswith("/videos/"):
                return
            embed = build_instagram_embed(self._embed, og_meta, original_url)
            file = await self._download_instafix_video(video_path)
            await self._send_preview(message, embed, file=file)

        else:
            LOGGER.debug("Instagram: unexpected image path %r for %s", img_path, shortcode)

    async def _handle_instagram_profile(
        self, message: discord.Message, match: re.Match[str]
    ) -> None:
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
            headers["Cookie"] = f"sessionid={unquote(session_id)}"
        try:
            resp = await self._http.get(url, headers=headers)
            resp.raise_for_status()
            return (resp.json().get("data") or {}).get("user")
        except Exception as exc:
            LOGGER.debug("Instagram profile API failed for @%s: %s", username, exc)
            return None

    async def _handle_threads(self, message: discord.Message, match: re.Match[str]) -> None:
        # Meta's login wall blocks OG scraping in production; the handler still
        # attempts a fetch so it works in test (mocked HTTP) and in case Meta
        # relaxes the restriction for bot user-agents in the future.
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

        user_info, game_name, file = await asyncio.gather(
            self._fetch_twitch_user_info(broadcaster_id, token)
            if broadcaster_id
            else _anone_pair(),
            self._fetch_twitch_game_name(game_id, token) if game_id else _anone(),
            self._download_cdn_video(mp4_url, filename="clip.mp4") if mp4_url else _anone(),
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
        await self._send_preview(message, embed, file=file)

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
        file: discord.File | None = None,
    ) -> None:
        kwargs: dict = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        try:
            sent = await message.channel.send(**kwargs)
        except (discord.Forbidden, discord.HTTPException):
            return
        if view is not None:
            view.message = sent

        # Send video as a reply so it appears below the embed (Discord renders
        # attachments above embeds when combined in the same message).
        if file is not None:
            try:
                await message.channel.send(file=file, reference=sent)  # type: ignore[union-attr]
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
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
        url = f"http://{INSTAFIX_HOST}{path}"
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

    async def _download_cdn_video(
        self, cdn_url: str, filename: str = "reel.mp4"
    ) -> discord.File | None:
        try:
            chunks: list[bytes] = []
            total = 0
            async with self._http.stream("GET", cdn_url) as resp:
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
            return discord.File(io.BytesIO(b"".join(chunks)), filename=filename)
        except Exception as exc:
            LOGGER.debug("CDN video download failed for %s: %s", cdn_url, exc)
            return None

    async def _download_instafix_video(self, video_path: str) -> discord.File | None:
        cdn_url = await self._resolve_instafix_redirect(video_path, require_mp4=True)
        if not cdn_url:
            return None
        return await self._download_cdn_video(cdn_url)

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
            url = f"http://{INSTAFIX_HOST}/p/{shortcode}/?img_index={i}"
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
