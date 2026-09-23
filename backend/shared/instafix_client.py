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
from urllib.parse import parse_qs, urlparse, urlunsplit

import aiohttp

from shared.safe_urls import (
    allowed_redirect_target,
    find_allowed_http_url,
    parse_allowed_absolute_url,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# InstaFix redirects browser User-Agents back to instagram.com; a bot-style UA
# is required to get the OG-tagged HTML back instead of a 302.
_BOT_UA = "Discordbot/2.0"
_TIMEOUT = aiohttp.ClientTimeout(total=6)

_INSTAGRAM_HOSTS = frozenset({"instagram.com", "www.instagram.com", "m.instagram.com"})
_INSTAGRAM_SHORTCODE_RE = re.compile(r"[A-Za-z0-9_-]+")


def extract_instagram_shortcode(text: str) -> str | None:
    """Extract a Reel shortcode from a direct `instagram.com/reel(s)/{code}` URL."""
    parsed = find_allowed_http_url(text, _INSTAGRAM_HOSTS)
    if parsed is None:
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0].lower() not in {"reel", "reels"}:
        return None
    return segments[1] if _INSTAGRAM_SHORTCODE_RE.fullmatch(segments[1]) else None


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

    share_url = find_allowed_http_url(url, _INSTAGRAM_HOSTS)
    if share_url is None:
        return None

    share_segments = [segment for segment in share_url.path.split("/") if segment]
    if len(share_segments) < 2 or share_segments[0].lower() != "share":
        return None

    full_url = urlunsplit(("https", "www.instagram.com", share_url.path, share_url.query, ""))
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        current_url = full_url
        for _ in range(4):
            async with _session.get(
                current_url,
                allow_redirects=False,
                timeout=_TIMEOUT,
                headers={"User-Agent": _UA},
            ) as resp:
                response_url = str(resp.url or current_url)
                if parse_allowed_absolute_url(response_url, _INSTAGRAM_HOSTS) is None:
                    return None
                if shortcode := extract_instagram_shortcode(response_url):
                    return shortcode
                location = resp.headers.get("Location") if 300 <= resp.status < 400 else None
                if not location:
                    return None
                next_url = allowed_redirect_target(current_url, location, _INSTAGRAM_HOSTS)
                if next_url is None:
                    return None
                if shortcode := extract_instagram_shortcode(next_url):
                    return shortcode
                current_url = next_url
        return None
    except Exception as exc:
        LOGGER.warning("[InstaFix] Failed to resolve share link: %s", type(exc).__name__)
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


def _orientation_from_og(og: dict[str, str]) -> bool | None:
    """Orientation from the standard ``og:video:width``/``height`` pair, same
    idea as Bilibili's dimension check in ``video_sources.py``.

    Returns ``None`` (unknown) rather than defaulting when the tags are
    missing or unparseable — in practice InstaFix's Reel OG page carries no
    such tags, so this is almost always ``None`` and orientation has to come
    from ``_orientation_from_mp4`` instead. Kept as the first check anyway in
    case a future InstaFix version starts emitting them; it costs nothing.
    """
    try:
        width = float(og.get("video:width", ""))
        height = float(og.get("video:height", ""))
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return height > width


def _read_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


def _iter_mp4_boxes(data: bytes, start: int, end: int) -> list[tuple[str, int, int]]:
    """List ``(box_type, payload_start, payload_end)`` for top-level boxes in
    ``data[start:end]``, per the ISO-BMFF box layout (``size``, ``type``,
    payload). Stops at the first box whose declared size runs past ``end`` —
    that's expected here, since ``data`` is only a bounded byte prefix of the
    real file, not the whole thing.
    """
    boxes: list[tuple[str, int, int]] = []
    pos = start
    while pos + 8 <= end:
        size = _read_u32(data, pos)
        box_type = data[pos + 4 : pos + 8].decode("latin-1", errors="replace")
        header_size = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = int.from_bytes(data[pos + 8 : pos + 16], "big")
            header_size = 16
        elif size == 0:
            size = end - pos
        if size < header_size or pos + size > end:
            break
        boxes.append((box_type, pos + header_size, pos + size))
        pos += size
    return boxes


def _tkhd_dimensions(tkhd_payload: bytes) -> tuple[int, int] | None:
    """Width/height (16.16 fixed-point, per spec) from a `tkhd` box's body.

    Layout after the box header: version(1)+flags(3), then creation/
    modification/track_id/reserved/duration sized by version (8-byte fields
    if version 1, else 4-byte), then reserved(8)+layer(2)+alternate_group(2)+
    volume(2)+reserved(2)+matrix(36), then width(4)+height(4).
    """
    if not tkhd_payload:
        return None
    version = tkhd_payload[0]
    var_block = 32 if version == 1 else 20
    fixed_block = 8 + 2 + 2 + 2 + 2 + 36
    width_offset = 4 + var_block + fixed_block
    if len(tkhd_payload) < width_offset + 8:
        return None
    width = _read_u32(tkhd_payload, width_offset) >> 16
    height = _read_u32(tkhd_payload, width_offset + 4) >> 16
    if width <= 0 or height <= 0:
        return None
    return width, height


def _extract_video_dimensions_from_mp4(data: bytes) -> tuple[int, int] | None:
    """Best-effort width/height from a (possibly truncated) mp4 byte prefix.

    Walks ``moov`` → `trak` → `tkhd`, returning the first track whose `tkhd`
    reports a non-zero size (an audio-only track's `tkhd` width/height are
    both 0x0, so it's naturally skipped without needing to read `hdlr`).
    Only sees the box structure actually present in ``data`` — a prefix that
    didn't reach far enough to contain `moov` (e.g. the source wasn't
    fast-start encoded) yields ``None`` rather than raising.
    """
    for box_type, p_start, p_end in _iter_mp4_boxes(data, 0, len(data)):
        if box_type != "moov":
            continue
        for trak_type, t_start, t_end in _iter_mp4_boxes(data, p_start, p_end):
            if trak_type != "trak":
                continue
            for leaf_type, l_start, l_end in _iter_mp4_boxes(data, t_start, t_end):
                if leaf_type != "tkhd":
                    continue
                dims = _tkhd_dimensions(data[l_start:l_end])
                if dims:
                    return dims
    return None


_MP4_HEADER_PROBE_BYTES = 262_144  # 256 KiB — covers a fast-start `moov` in the common case


async def _orientation_from_mp4(cdn_url: str, session: aiohttp.ClientSession) -> bool | None:
    """Ground-truth orientation read from the resolved CDN mp4 itself.

    InstaFix's Reel OG page doesn't carry ``og:video:width``/``height`` in
    practice, so ``_orientation_from_og`` returns ``None`` almost every time
    and every Reel — including landscape ones — was rendered with the
    vertical blurred-side-column treatment regardless of its real shape.
    This downloads a bounded byte prefix of the same mp4 URL already
    resolved for duration and reads the real container dimensions from its
    `tkhd` box, the same "trust the asset, not unreliable metadata" approach
    ``_extract_duration_seconds`` already takes with the `efg` param. Some
    CDNs ignore the ``Range`` header and return the full body; the read is
    capped at the probe size regardless, so this never downloads more than
    that. Fails open to ``None`` (caller defaults to vertical, matching
    prior behaviour) on any error, timeout, or a `moov` that didn't fit in
    the probed prefix.
    """
    try:
        async with session.get(
            cdn_url,
            headers={"Range": f"bytes=0-{_MP4_HEADER_PROBE_BYTES - 1}"},
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status not in (200, 206):
                return None
            data = await resp.content.read(_MP4_HEADER_PROBE_BYTES)
    except Exception as exc:
        LOGGER.debug("[InstaFix] mp4 header probe failed: %s", type(exc).__name__)
        return None
    dims = _extract_video_dimensions_from_mp4(data)
    if dims is None:
        return None
    width, height = dims
    return height > width


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

    ``is_vertical`` comes from OG page dimensions when present (rare in
    practice), else a probe of the resolved mp4's own container dimensions,
    else defaults to True — see ``_orientation_from_og`` /
    ``_orientation_from_mp4``.

    ``creator_id``/``creator_name`` are both the same OG handle/display-name
    string (see ``_extract_title``) — Instagram exposes no stable numeric id
    to this integration, unlike YouTube's channelId or Bilibili's owner.mid.
    A display name can change or collide, so a ``creator`` blocklist rule
    against a Reel is only as reliable as that string was at fetch time.
    """

    title: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    is_vertical: bool = True
    creator_id: str | None = None
    creator_name: str | None = None


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
        handle = _extract_title(og)

        is_vertical = _orientation_from_og(og)
        if is_vertical is None and video_cdn_url:
            is_vertical = await _orientation_from_mp4(video_cdn_url, _session)
        if is_vertical is None:
            is_vertical = True

        return InstagramReelInfo(
            title=title,
            thumbnail_url=thumbnail_url,
            duration_seconds=duration_seconds,
            is_vertical=is_vertical,
            creator_id=handle,
            creator_name=handle,
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
