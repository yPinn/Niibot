"""Instagram Reel resolution via the self-hosted InstaFix proxy.

UNOFFICIAL, same dependency class as the Twitch clip GraphQL call and the
Bilibili web endpoints in this package: InstaFix (github.com/Wikidepia/
InstaFix, see docs/integrations/instafix.md) is a self-hosted proxy that
re-serves Instagram post/reel data as OpenGraph-tagged HTML, bypassing the
login wall that blocks server-side scraping. Instagram's CDN URLs behind it
are signed and expire, so the mp4 source must be resolved fresh at play
time — never cached — exactly like ``fetch_twitch_clip_source``.

This module is intentionally a fresh, minimal implementation scoped to what
Video Queue needs (a Reel's title/thumbnail/duration at enqueue time, its
direct mp4 URL at play time) — it does not import from or modify
``discord/cogs/social_preview/`` which has a separate, more elaborate
httpx-based Instagram integration (carousel/grid probing, profile
enrichment) serving Discord's link-preview feature. Consolidating the two
into one shared client is deliberately deferred to a follow-up once this
path is proven in production — see docs/integrations/instafix.md.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import aiohttp

LOGGER: logging.Logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# InstaFix redirects browser User-Agents back to instagram.com; a bot-style UA
# is required to get the OG-tagged HTML back instead of a 302.
_BOT_UA = "Discordbot/2.0"
_TIMEOUT = aiohttp.ClientTimeout(total=6)

_INSTAGRAM_REEL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?instagram\.com/reels?/([A-Za-z0-9_-]+)", re.IGNORECASE
)
_INSTAGRAM_SHARE_RE = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/share/", re.IGNORECASE)


def extract_instagram_shortcode(text: str) -> str | None:
    """Extract a Reel shortcode from a direct `instagram.com/reel(s)/{code}` URL."""
    m = _INSTAGRAM_REEL_RE.search(text)
    return m.group(1) if m else None


async def resolve_instagram_url(
    url: str,
    session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Extract a Reel shortcode from a direct or `instagram.com/share/...` URL.

    The mobile app's "Copy Link" action produces a `/share/...` short link
    that redirects to the canonical `/reel/{shortcode}/` URL — same shape as
    `resolve_bilibili_url()`'s `b23.tv` handling. Fails open (``None``) on
    any error so callers just treat it as "not this platform".
    """
    shortcode = extract_instagram_shortcode(url)
    if shortcode:
        return shortcode

    if not _INSTAGRAM_SHARE_RE.search(url):
        return None

    full_url = url if url.startswith("http") else f"https://{url}"
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(
            full_url,
            allow_redirects=True,
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA},
        ) as resp:
            return extract_instagram_shortcode(str(resp.url))
    except Exception as exc:
        LOGGER.warning("[InstaFix] Failed to resolve share link %s: %s", url, type(exc).__name__)
        return None
    finally:
        if _own_session:
            await _session.close()


class _OGParser(HTMLParser):
    """Minimal OpenGraph tag extractor.

    Deliberately duplicated from
    ``discord/cogs/social_preview/_ogparser.py::_OGParser`` rather than
    imported — see the module docstring on the staged-migration decision.
    """

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
            # InstaFix sets the username in twitter:title, not og:title.
            self.og.setdefault("title", content)


def _parse_og(html: str) -> dict[str, str]:
    parser = _OGParser()
    parser.feed(html[:20_000])
    return parser.og


def _extract_title(og: dict[str, str]) -> str | None:
    raw = og.get("title")
    if not raw:
        return None
    return raw.split(" on Instagram")[0] if " on Instagram" in raw else raw


def _strip_trailing_hashtags(text: str) -> str:
    """Drop a caption's trailing hashtag-only lines.

    Deliberately duplicated from
    ``discord/cogs/social_preview/_embeds.py::_strip_trailing_hashtags``
    rather than imported — see the module docstring on the staged-migration
    decision. If every line is hashtags, this empties the string (the caller
    then falls back to the handle).
    """
    lines = text.splitlines()
    while lines:
        tokens = lines[-1].strip().split()
        if tokens and all(t.startswith("#") for t in tokens):
            lines.pop()
        else:
            break
    return "\n".join(lines).rstrip()


# Short on purpose: this stands in for a title, not a caption display — a
# scannable label in a queue list/chat line, not the full text.
_TITLE_MAX_LENGTH = 60


def _extract_display_title(og: dict[str, str]) -> str | None:
    """Prefer the caption (``og:description``) as the queue entry's title —
    unlike ``@handle``, it actually describes the content, matching every
    other platform's title. Falls back to ``_extract_title()`` (the handle)
    when there's no usable caption (absent, or nothing left after stripping
    trailing hashtags).

    The three call sites that render `title` (chat `!vq` list, dashboard
    cards, history) all treat it as a short, single-line string — a raw
    caption can run to 2200 characters with embedded newlines, so it's
    cleaned and capped here, once, rather than teaching every caller to
    defensively handle a new shape.
    """
    caption = _strip_trailing_hashtags(og.get("description", "")).strip()
    if not caption:
        return _extract_title(og)
    caption = " ".join(caption.split())  # collapse embedded newlines/whitespace
    if len(caption) > _TITLE_MAX_LENGTH:
        caption = caption[: _TITLE_MAX_LENGTH - 1].rstrip() + "…"
    return caption


def _extract_duration_seconds(cdn_url: str) -> int | None:
    """Best-effort: Instagram's CDN URL embeds an undocumented base64 JSON
    blob (query param ``efg``) that includes the real duration (``duration_s``).
    Not part of any public contract — Instagram can drop or rename it without
    notice, same risk class as everything else in this module. Fails open.
    """
    try:
        efg = parse_qs(urlparse(cdn_url).query).get("efg", [None])[0]
        if not efg:
            return None
        padded = efg + "=" * (-len(efg) % 4)  # restore stripped base64 padding
        duration = json.loads(base64.b64decode(padded)).get("duration_s")
        return int(duration) if isinstance(duration, int | float) else None
    except Exception:
        return None


@dataclass
class InstagramReelInfo:
    """Best-effort metadata for a queued Instagram Reel.

    InstaFix's OG data carries no view count — permanently unknown at queue
    time. ``duration_seconds`` *is* obtainable: it rides along in the same
    ``/videos/{shortcode}/1`` redirect ``fetch_instagram_reel_source()``
    already resolves at play time (see ``_extract_duration_seconds``), so
    fetching it here just means resolving that redirect one request earlier
    too. It's still best-effort — that redirect can fail the same way it can
    at play time — in which case ``duration_seconds`` is backfilled
    client-side from the resolved `<video>` element instead
    (`reportVideoMetadata`, same mechanism Twitch Clip already uses).
    """

    title: str | None
    thumbnail_url: str | None
    duration_seconds: int | None


async def _resolve_instafix_redirect(
    instafix_host: str,
    path: str,
    session: aiohttp.ClientSession,
    *,
    require_mp4: bool = False,
) -> str | None:
    """Follow a single InstaFix 302 and return the CDN URL, or None.

    ``require_mp4`` discards a redirect whose target isn't an ``.mp4`` (the
    `/videos/` path can redirect to a `.jpg` for a non-video item).
    """
    if not path.startswith("/"):
        LOGGER.warning("[InstaFix] Unexpected path (not relative): %r", path)
        return None
    url = f"http://{instafix_host}{path}"
    try:
        async with session.get(
            url,
            headers={"User-Agent": _BOT_UA},
            allow_redirects=False,
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status not in (301, 302, 303, 307, 308):
                return None
            cdn_url = resp.headers.get("Location")
            if not cdn_url:
                return None
            if require_mp4 and ".mp4" not in cdn_url.split("?")[0]:
                return None
            return cdn_url
    except Exception as exc:
        LOGGER.debug("[InstaFix] redirect resolve failed for %s: %s", path, type(exc).__name__)
        return None


async def fetch_instagram_reel_info(
    shortcode: str,
    instafix_host: str,
    session: aiohttp.ClientSession | None = None,
) -> InstagramReelInfo:
    """Fetch a Reel's title + thumbnail + duration from InstaFix.

    Fails open to all-None on the OG-page fetch. Once the OG page is in
    hand, the thumbnail redirect and the video redirect (for duration —
    see ``_extract_duration_seconds``) are resolved concurrently, since
    they're independent requests and this runs at enqueue time (latency the
    requester waits on), unlike ``fetch_instagram_reel_source()``'s
    play-time-only resolve of the same video redirect.
    """
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        og_url = f"http://{instafix_host}/reel/{shortcode}/"
        try:
            async with _session.get(
                og_url,
                headers={"User-Agent": _BOT_UA},
                allow_redirects=False,
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    # InstaFix couldn't proxy this Reel and bounced back to IG.
                    return InstagramReelInfo(None, None, None)
                if resp.status != 200:
                    return InstagramReelInfo(None, None, None)
                html = await resp.text()
        except Exception as exc:
            LOGGER.warning(
                "[InstaFix] OG fetch failed for reel %s: %s", shortcode, type(exc).__name__
            )
            return InstagramReelInfo(None, None, None)

        og = _parse_og(html)
        title = _extract_display_title(og)
        img_path = og.get("image", "")

        async def _resolve_thumbnail() -> str | None:
            if img_path.startswith("/"):
                return await _resolve_instafix_redirect(instafix_host, img_path, _session)
            if img_path.startswith(("http://", "https://")):
                return img_path
            return None

        thumbnail_url, video_cdn_url = await asyncio.gather(
            _resolve_thumbnail(),
            _resolve_instafix_redirect(
                instafix_host, f"/videos/{shortcode}/1", _session, require_mp4=True
            ),
        )
        duration_seconds = _extract_duration_seconds(video_cdn_url) if video_cdn_url else None

        return InstagramReelInfo(
            title=title, thumbnail_url=thumbnail_url, duration_seconds=duration_seconds
        )
    finally:
        if _own_session:
            await _session.close()


async def fetch_instagram_reel_source(
    shortcode: str,
    instafix_host: str,
    session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Resolve a Reel shortcode to a directly-playable CDN mp4 URL.

    Play-time-only call — the returned URL is signed and expires, so it must
    never be cached (same contract as ``fetch_twitch_clip_source``).
    """
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        return await _resolve_instafix_redirect(
            instafix_host, f"/videos/{shortcode}/1", _session, require_mp4=True
        )
    finally:
        if _own_session:
            await _session.close()
