"""Video source utilities: URL parsing + metadata fetching.

Split out of ``shared.repositories.video_queue`` — these helpers do pure string
parsing and public-API calls, with no database dependency. Used by the Twitch
bot, channel-points redemptions, and the donation webhook.

  - extract_youtube_id / extract_youtube_info : pure YouTube URL parsing
  - fetch_yt_info                              : YouTube Data API v3 call
  - extract_bilibili_bvid / resolve_bilibili_url : Bilibili BV parsing (+ b23.tv,
    legacy av{id} conversion via _av_to_bv, and ?p= multi-part folding — see
    split_bilibili_id)
  - fetch_bilibili_info                        : Bilibili metadata (via
    shared.bilibili_client — three risk-control-aware tiers)
  - extract_twitch_clip_slug                   : Twitch clip URL parsing
  - fetch_twitch_clip_info                     : Twitch Helix clips API call
  - resolve_instagram_url                      : Instagram Reel / share-link parsing (+
    shared.instafix_client — self-hosted InstaFix proxy)
  - fetch_instagram_reel_info                  : Instagram Reel metadata (title/thumbnail
    only — no duration/view_count, see shared.instafix_client)

  - resolve_video_url / fetch_video_metadata / build_watch_url : registry
    layer composing the platform-specific functions above behind one shape,
    for callers that just want "figure out what this URL is and fetch its
    metadata" without repeating the per-platform cascade themselves.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, quote, urlunsplit
from weakref import WeakKeyDictionary

import aiohttp

from shared.bilibili_client import fetch_bilibili_video_data
from shared.instafix_client import fetch_instagram_reel_info, resolve_instagram_url
from shared.safe_urls import (
    allowed_redirect_target,
    find_allowed_http_url,
    parse_allowed_absolute_url,
)
from shared.twitch_egress import EgressPriority, TwitchEgressCoordinator, credential_bucket_key

LOGGER: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YouTube utilities
# ---------------------------------------------------------------------------

_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
        "youtu.be",
    }
)
_VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")

_ISO8601_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")

# Playability reasons the OBS overlay cannot recover from — the iframe either
# refuses to embed or silently shows an error, and the queue only advances once
# the timer ceiling expires. Reject these at submission instead. Most are
# YouTube-only (Twitch clips always embed, and Bilibili's metadata endpoint is
# too unreliable to gate on generally — see
# docs/architecture/video-queue-platforms.md); INVALID_TIMESTAMP/INVALID_PAGE
# are Twitch VOD/Bilibili-specific out-of-range submissions, and NOT_VIDEO is
# Instagram-specific (a pasted `/p/` link that turned out to be a photo post).
UNPLAYABLE_NOT_EMBEDDABLE = "not_embeddable"
UNPLAYABLE_AGE_RESTRICTED = "age_restricted"
UNPLAYABLE_PRIVATE = "private"
UNPLAYABLE_REMOVED = "removed"
UNPLAYABLE_INVALID_TIMESTAMP = "invalid_timestamp"
UNPLAYABLE_INVALID_PAGE = "invalid_page"
UNPLAYABLE_NOT_VIDEO = "not_video"

_UNPLAYABLE_MESSAGES: dict[str, str] = {
    UNPLAYABLE_NOT_EMBEDDABLE: "這部影片不開放外部播放",
    UNPLAYABLE_AGE_RESTRICTED: "這部影片有年齡限制，無法播放",
    UNPLAYABLE_PRIVATE: "這是私人影片，無法播放",
    UNPLAYABLE_REMOVED: "這部影片已被移除或無法使用",
    UNPLAYABLE_INVALID_TIMESTAMP: "影片時間點已超出可播放範圍",
    UNPLAYABLE_INVALID_PAGE: "指定的分P不存在",
    UNPLAYABLE_NOT_VIDEO: "這則貼文不是影片",
}


def unplayable_message(reason: str | None) -> str:
    """Human-readable Chinese rejection message for an ``UNPLAYABLE_*`` reason."""
    return _UNPLAYABLE_MESSAGES.get(reason or "", "這部影片無法播放")


@dataclass
class YouTubeInfo:
    """Normalized result of a YouTube Data API v3 ``videos.list`` call.

    Defaults are the "we couldn't tell" state: on any fetch failure the caller
    gets a bare ``YouTubeInfo()`` (playable, no metadata) so a transient API
    blip never rejects a submission — only a positively-returned video with a
    disqualifying status sets ``playable = False``.
    """

    title: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    is_vertical: bool = False
    playable: bool = True
    unplayable_reason: str | None = None
    thumbnail_url: str | None = None
    creator_id: str | None = None  # snippet.channelId
    creator_name: str | None = None  # snippet.channelTitle


def extract_youtube_id(text: str) -> str | None:
    """Extract 11-char YouTube video ID from a URL string. Returns None if not found."""
    return extract_youtube_info(text)[0]


def extract_youtube_info(text: str) -> tuple[str | None, bool]:
    """Extract YouTube video ID and whether the URL is a Short (vertical video).

    Returns:
        (video_id, is_vertical) — video_id is None if no match found.
    """
    parsed = find_allowed_http_url(text, _YOUTUBE_HOSTS)
    if parsed is None or parsed.hostname is None:
        return None, False

    host = parsed.hostname.lower()
    segments = [segment for segment in parsed.path.split("/") if segment]
    if host == "youtu.be":
        video_id = segments[0] if segments else ""
        return (video_id, False) if _VIDEO_ID_RE.fullmatch(video_id) else (None, False)

    if len(segments) >= 2 and segments[0] == "shorts":
        video_id = segments[1]
        return (video_id, True) if _VIDEO_ID_RE.fullmatch(video_id) else (None, False)

    # /live/{id} (live stream or its post-stream VOD share) and /embed/{id} (copy-embed-code
    # output, youtube-nocookie's only path shape) — same flat "one id segment" shape as
    # youtu.be, just under a different first path segment. /v/{id} is the pre-2010 watch
    # URL, still resolvable today. None of these are Shorts, so is_vertical stays False.
    if len(segments) >= 2 and segments[0] in ("live", "embed", "v"):
        video_id = segments[1]
        return (video_id, False) if _VIDEO_ID_RE.fullmatch(video_id) else (None, False)

    if parsed.path.rstrip("/") == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        return (video_id, False) if _VIDEO_ID_RE.fullmatch(video_id) else (None, False)

    return None, False


def _https(url: str | None) -> str | None:
    """Upgrade an `http://` asset URL to `https://` (Bilibili `pic` is often plain
    http, which a secure page won't load). Returns None for a falsy input."""
    if not url:
        return None
    return "https://" + url[7:] if url.startswith("http://") else url


def _parse_iso8601_duration(duration: str) -> int:
    """Parse ISO 8601 duration (e.g. 'PT1H3M45S') to total seconds."""
    m = _ISO8601_RE.match(duration)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _assess_yt_playability(item: dict) -> str | None:
    """Return an ``UNPLAYABLE_*`` reason if this videos.list item can't be
    embedded and played in the overlay, else None.

    Only checks positive signals — an item missing a ``status`` block (older
    API responses, partial data) is treated as playable.
    """
    status = item.get("status", {})
    content_rating = item.get("contentDetails", {}).get("contentRating", {})

    if status.get("uploadStatus") in ("deleted", "rejected", "failed"):
        return UNPLAYABLE_REMOVED
    # 'unlisted' still embeds fine — only 'private' is unplayable for a viewer.
    if status.get("privacyStatus") == "private":
        return UNPLAYABLE_PRIVATE
    if content_rating.get("ytRating") == "ytAgeRestricted":
        return UNPLAYABLE_AGE_RESTRICTED
    if status.get("embeddable") is False:
        return UNPLAYABLE_NOT_EMBEDDABLE
    return None


async def fetch_yt_info(
    video_id: str,
    api_key: str,
    session: aiohttp.ClientSession | None = None,
) -> YouTubeInfo:
    """Fetch title, duration, view count, orientation, and playability via YouTube Data API v3.

    If `session` is None a temporary one-shot session is created and closed.
    Returns a bare ``YouTubeInfo()`` (metadata None, playable) on any failure;
    ``is_vertical`` is True when the API reports portrait thumbnails (Shorts).
    """
    if not api_key:
        return YouTubeInfo()

    url = "https://www.googleapis.com/youtube/v3/videos"
    # Pass api_key via params dict so it never appears as a literal URL string
    # (prevents accidental key exposure in logs, traces, or error messages).
    params = {
        "part": "snippet,contentDetails,statistics,status",
        "id": video_id,
        "key": api_key,
    }
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                LOGGER.info("[YouTube API] Unexpected status %s for %s", resp.status, video_id)
                return YouTubeInfo()
            data = await resp.json()
            items = data.get("items", [])
            if not items:
                return YouTubeInfo()  # video not found / private
            item = items[0]
            snippet: dict = item.get("snippet", {})
            title: str | None = snippet.get("title")
            channel_id: str | None = snippet.get("channelId")
            channel_title: str | None = snippet.get("channelTitle")
            raw_duration: str = item.get("contentDetails", {}).get("duration", "")
            duration_seconds = _parse_iso8601_duration(raw_duration) if raw_duration else 0
            raw_views: str | None = item.get("statistics", {}).get("viewCount")
            view_count = int(raw_views) if raw_views else None
            # Detect portrait orientation from thumbnail dimensions (Shorts have h > w)
            thumbnails: dict = snippet.get("thumbnails", {})
            is_vertical = any(
                (t.get("height", 0) or 0) > (t.get("width", 1) or 1) for t in thumbnails.values()
            )
            thumb = thumbnails.get("medium") or thumbnails.get("high") or thumbnails.get("default")
            reason = _assess_yt_playability(item)
            return YouTubeInfo(
                title=title,
                duration_seconds=duration_seconds or None,
                view_count=view_count,
                is_vertical=is_vertical,
                playable=reason is None,
                unplayable_reason=reason,
                thumbnail_url=_https(thumb.get("url")) if isinstance(thumb, dict) else None,
                creator_id=channel_id,
                creator_name=channel_title,
            )
    except Exception as exc:
        LOGGER.warning(
            "[YouTube API] fetch_yt_info failed for %s: %s", video_id, type(exc).__name__
        )
        return YouTubeInfo()
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Bilibili utilities
# ---------------------------------------------------------------------------

_BILIBILI_HOSTS = frozenset({"bilibili.com", "www.bilibili.com", "m.bilibili.com"})
_BILIBILI_REDIRECT_HOSTS = _BILIBILI_HOSTS | frozenset({"b23.tv"})
_BILIBILI_BV_RE = re.compile(r"BV[A-Za-z0-9]{10}")
_BILIBILI_AV_RE = re.compile(r"[Aa][Vv](\d+)")
_BILIBILI_SHORT_CODE_RE = re.compile(r"[A-Za-z0-9]+")
_BILIBILI_PAGE_SUFFIX_RE = re.compile(r"_p(\d+)$")

# Bilibili's BV<->av id encoding — a published (reverse-engineered) base58 XOR
# scheme with no network round-trip (see bilibili-API-collect's
# docs/misc/bvid_desc.md). Bilibili's address bar has shown BV ids only since
# ~2020, but the legacy numeric `av{id}` path still resolves, so a pasted
# `bilibili.com/video/av170001` link needs converting to be usable as this
# module's canonical id.
_BILIBILI_BV_XOR_CODE = 23442827791579
_BILIBILI_BV_MAX_AID = 1 << 51
_BILIBILI_BV_ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"


def _av_to_bv(aid: int) -> str:
    """Convert a legacy numeric Bilibili aid to its BV id. Deterministic, pure."""
    chars = list("BV1" + "0" * 9)
    index = len(chars) - 1
    value = (_BILIBILI_BV_MAX_AID | aid) ^ _BILIBILI_BV_XOR_CODE
    while value > 0:
        chars[index] = _BILIBILI_BV_ALPHABET[value % 58]
        value //= 58
        index -= 1
    chars[3], chars[9] = chars[9], chars[3]
    chars[4], chars[7] = chars[7], chars[4]
    return "".join(chars)


def split_bilibili_id(video_id: str) -> tuple[str, int]:
    """Split a stored Bilibili id back into ``(bvid, page)``.

    A multi-part video's non-first part is stored as ``BVxxxxxxxxxx_pN`` (see
    ``extract_bilibili_bvid``); anything else — including every id stored
    before multi-part support existed — has no suffix and is page 1. Keeping
    P1 suffix-free means existing rows and dedupe/blocklist/ranking keys are
    unaffected.
    """
    m = _BILIBILI_PAGE_SUFFIX_RE.search(video_id)
    return (video_id[: m.start()], int(m.group(1))) if m else (video_id, 1)


def _bilibili_id_with_page(bvid: str, page: int) -> str:
    return bvid if page <= 1 else f"{bvid}_p{page}"


def extract_bilibili_bvid(text: str) -> str | None:
    """Extract a Bilibili video id from a full bilibili.com URL.

    Returns the composite id ``split_bilibili_id()`` understands: a bare BV id,
    or ``BVxxxxxxxxxx_pN`` when the URL's ``?p=`` selects part N≥2 of a
    multi-part video. Also accepts the legacy numeric ``av{id}`` path,
    converted via ``_av_to_bv``. Returns None if not found.
    """
    parsed = find_allowed_http_url(text, _BILIBILI_HOSTS)
    if parsed is None:
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0] != "video":
        return None
    raw_id = segments[1]
    if _BILIBILI_BV_RE.fullmatch(raw_id):
        bvid = raw_id
    elif av_match := _BILIBILI_AV_RE.fullmatch(raw_id):
        bvid = _av_to_bv(int(av_match.group(1)))
    else:
        return None
    page_raw = parse_qs(parsed.query).get("p", [""])[0]
    page = int(page_raw) if page_raw.isdigit() else 1
    return _bilibili_id_with_page(bvid, page)


async def resolve_bilibili_url(
    url: str,
    session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Extract BV ID from a Bilibili URL, following b23.tv short URL redirects.

    Handles both full bilibili.com URLs and b23.tv short URLs.
    """
    bvid = extract_bilibili_bvid(url)
    if bvid:
        return bvid

    short_url = find_allowed_http_url(url, frozenset({"b23.tv"}))
    if short_url is None:
        return None

    short_segments = [segment for segment in short_url.path.split("/") if segment]
    if not short_segments or not _BILIBILI_SHORT_CODE_RE.fullmatch(short_segments[0]):
        return None

    # Drop the incoming query — b23.tv is a pure redirect and any query on the
    # short link is share-tracking cruft (e.g. `spm_id_from`), not routing
    # state; forwarding it would leak the original sharer's tracking params
    # to Bilibili on our behalf.
    full_url = urlunsplit(("https", "b23.tv", f"/{short_segments[0]}", "", ""))
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        current_url = full_url
        for _ in range(4):
            async with _session.get(
                current_url,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=5),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            ) as resp:
                response_url = str(resp.url or current_url)
                if parse_allowed_absolute_url(response_url, _BILIBILI_REDIRECT_HOSTS) is None:
                    return None
                if resolved := extract_bilibili_bvid(response_url):
                    return resolved
                location = resp.headers.get("Location") if 300 <= resp.status < 400 else None
                if not location:
                    return None
                next_url = allowed_redirect_target(current_url, location, _BILIBILI_REDIRECT_HOSTS)
                if next_url is None:
                    return None
                if resolved := extract_bilibili_bvid(next_url):
                    return resolved
                current_url = next_url
        return None
    except Exception as exc:
        LOGGER.warning("[Bilibili] Failed to resolve short URL: %s", type(exc).__name__)
        return None
    finally:
        if _own_session:
            await _session.close()


@dataclass
class BilibiliInfo:
    """Normalized result of a Bilibili metadata fetch (see fetch_bilibili_info).

    Defaults are the "we couldn't tell" state, same convention as
    :class:`YouTubeInfo` — a bare ``BilibiliInfo()`` on any fetch failure.
    """

    title: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    is_vertical: bool = False
    thumbnail_url: str | None = None
    creator_id: str | None = None  # owner.mid
    creator_name: str | None = None  # owner.name
    page_count: int | None = None  # total 分P count, when the view endpoint returned one


async def fetch_bilibili_info(
    bvid: str,
    session: aiohttp.ClientSession | None = None,
    *,
    page: int = 1,
) -> BilibiliInfo:
    """Fetch title, duration, view count, orientation, cover image, and uploader
    identity from Bilibili.

    ``bvid`` is always the bare video id — a caller holding a composite
    ``BVxxx_pN`` stored id splits it first via ``split_bilibili_id()``. When
    ``page`` selects a part beyond P1 of a multi-part video, duration/
    orientation/title are overridden from that part's ``data["pages"][page-1]``
    entry when the view endpoint's response included one; a caller can compare
    the returned ``page_count`` against the requested ``page`` to detect a
    part that doesn't exist.

    All fields are None/False when every tier of :mod:`shared.bilibili_client`
    is blocked or the video is unavailable — Bilibili has no official metadata
    API and a datacenter IP is often risk-controlled, so callers must treat
    this as "unknown", not "reject" (see ``metadata_best_effort`` on
    :class:`VideoMetadata`).
    """
    data = await fetch_bilibili_video_data(bvid, session=session)
    if not data:
        return BilibiliInfo()
    title: str | None = data.get("title")
    duration_seconds: int | None = data.get("duration")
    view_count_raw = (data.get("stat") or {}).get("view")
    view_count: int | None = int(view_count_raw) if view_count_raw is not None else None
    dimension = data.get("dimension") or {}
    width = dimension.get("width") or 0
    height = dimension.get("height") or 0
    is_vertical = height > width if width > 0 and height > 0 else False
    owner = data.get("owner") or {}
    creator_id = str(owner["mid"]) if owner.get("mid") is not None else None
    creator_name: str | None = owner.get("name")

    pages = data.get("pages")
    page_count = len(pages) if isinstance(pages, list) else None
    if page > 1 and isinstance(pages, list) and 1 <= page <= len(pages):
        part = pages[page - 1] or {}
        part_duration = part.get("duration")
        if isinstance(part_duration, int):
            duration_seconds = part_duration
        part_dim = part.get("dimension") or {}
        part_width = part_dim.get("width") or 0
        part_height = part_dim.get("height") or 0
        if part_width > 0 and part_height > 0:
            is_vertical = part_height > part_width
        part_title = part.get("part")
        if title and part_title:
            title = f"{title} P{page} {part_title}"

    return BilibiliInfo(
        title=title,
        duration_seconds=duration_seconds,
        view_count=view_count,
        is_vertical=is_vertical,
        thumbnail_url=_https(data.get("pic")),
        creator_id=creator_id,
        creator_name=creator_name,
        page_count=page_count,
    )


# ---------------------------------------------------------------------------
# Twitch Clip utilities
# ---------------------------------------------------------------------------


_TWITCH_CLIP_HOSTS = frozenset({"clips.twitch.tv", "twitch.tv", "www.twitch.tv", "m.twitch.tv"})
_TWITCH_VOD_HOSTS = frozenset({"twitch.tv", "www.twitch.tv", "m.twitch.tv"})
_TWITCH_SLUG_RE = re.compile(r"[A-Za-z0-9_-]+")

_TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
_TWITCH_HELIX_CLIPS_URL = "https://api.twitch.tv/helix/clips"
_TWITCH_HELIX_VIDEOS_URL = "https://api.twitch.tv/helix/videos"

# twitch.tv/videos/{id} (also m.twitch.tv). The id is numeric.
_HMS_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.IGNORECASE)

# A VOD is hours long; Video Queue treats it as a "long clip" — play a window of
# at most this many seconds from its start point (the `?t=` timestamp, else 0).
TWITCH_VOD_WINDOW_SECONDS = 600


def _parse_hms(text: str) -> int:
    """Parse Twitch's `1h2m3s` / `90m` / `3600s` / bare-seconds duration to int."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    m = _HMS_RE.fullmatch(text)
    if not m or not any(m.groups()):
        return 0
    h, mi, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + s


# Module-level app token cache keyed by (client_id, client_secret).
# Twitch app tokens are valid for ~60 days; we refresh 5 min before expiry.
_app_token_cache: dict[tuple[str, str], tuple[str, float]] = {}  # key → (token, expires_at)
_app_token_locks: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    dict[tuple[str, str], asyncio.Lock],
] = WeakKeyDictionary()
_twitch_media_egress = TwitchEgressCoordinator()


def _app_token_lock(cache_key: tuple[str, str]) -> asyncio.Lock:
    """Return a loop-local lock so concurrent cache misses collapse to one fetch."""
    loop = asyncio.get_running_loop()
    locks = _app_token_locks.setdefault(loop, {})
    return locks.setdefault(cache_key, asyncio.Lock())


async def _twitch_helix_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict[str, str],
    client_id: str,
    token: str,
) -> tuple[int, dict]:
    """Return one Helix JSON response, retrying an idempotent 429 once."""
    bucket_key = credential_bucket_key(token)
    for attempt in range(2):
        await _twitch_media_egress.acquire_helix(
            bucket_key,
            priority=EgressPriority.BACKGROUND,
        )
        async with session.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}", "Client-Id": client_id},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            _twitch_media_egress.observe_helix(
                bucket_key,
                status_code=resp.status,
                headers=getattr(resp, "headers", {}),
            )
            if resp.status == 429 and attempt == 0:
                continue
            return resp.status, await resp.json()
    raise AssertionError("unreachable Twitch Helix retry state")


def extract_twitch_clip_slug(text: str) -> str | None:
    """Extract clip slug from a Twitch clip URL. Returns None if not found.

    Supports:
      - https://clips.twitch.tv/{slug}
      - https://clips.twitch.tv/embed?clip={slug} (the "Embed" share option)
      - https://www.twitch.tv/{channel}/clip/{slug}
      - https://www.twitch.tv/clip/{slug} (channel-less share form)
      - m.twitch.tv equivalents of the two twitch.tv shapes above
    """
    parsed = find_allowed_http_url(text, _TWITCH_CLIP_HOSTS)
    if parsed is None or parsed.hostname is None:
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    host = parsed.hostname.lower()
    if host == "clips.twitch.tv":
        if segments and segments[0].lower() == "embed":
            slug = parse_qs(parsed.query).get("clip", [""])[0]
        else:
            slug = segments[0] if segments else ""
    elif len(segments) >= 3 and segments[1] == "clip":
        slug = segments[2]
    elif len(segments) == 2 and segments[0] == "clip":
        slug = segments[1]
    else:
        return None
    return slug if _TWITCH_SLUG_RE.fullmatch(slug) else None


def extract_twitch_vod_info(text: str) -> tuple[str | None, int]:
    """Extract a Twitch VOD id and its `?t=` start offset (seconds).

    Returns (video_id, start_seconds); video_id is None if the URL isn't a
    twitch.tv/videos/{id} link. start_seconds defaults to 0.
    """
    parsed = find_allowed_http_url(text, _TWITCH_VOD_HOSTS)
    if parsed is None:
        return None, 0
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2 or segments[0] != "videos" or not segments[1].isdigit():
        return None, 0
    timestamp = parse_qs(parsed.query).get("t", [""])[0]
    return segments[1], _parse_hms(timestamp) if timestamp else 0


async def _get_twitch_app_token(
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession,
) -> str | None:
    """Return a cached Twitch app token, fetching a new one only when expired.

    Tokens are valid ~60 days; we treat them as expired 5 min before their
    reported ``expires_in`` to guard against clock skew.
    """
    cache_key = (client_id, client_secret)
    cached_token, expires_at = _app_token_cache.get(cache_key, (None, 0.0))
    if cached_token and time.monotonic() < expires_at:
        return cached_token

    async with _app_token_lock(cache_key):
        cached_token, expires_at = _app_token_cache.get(cache_key, (None, 0.0))
        if cached_token and time.monotonic() < expires_at:
            return cached_token

        async with session.post(
            _TWITCH_OAUTH_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                LOGGER.warning("[Twitch API] Failed to get app token: %s", resp.status)
                return None
            token_data = await resp.json()

        new_token = token_data.get("access_token")
        if not new_token:
            return None

        expires_in = token_data.get("expires_in", 3600)
        _app_token_cache[cache_key] = (new_token, time.monotonic() + expires_in - 300)
        return new_token


@dataclass
class TwitchMediaInfo:
    """Normalized result of a Twitch Clip or VOD Helix fetch — both endpoints
    yield the same shape (see fetch_twitch_clip_info / fetch_twitch_vod_info).

    Defaults are the "we couldn't tell" state, same convention as
    :class:`YouTubeInfo` — a bare ``TwitchMediaInfo()`` on any fetch failure.
    """

    title: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    thumbnail_url: str | None = None
    creator_id: str | None = None
    creator_name: str | None = None


async def fetch_twitch_clip_info(
    slug: str,
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession | None = None,
) -> TwitchMediaInfo:
    """Fetch clip title, duration, view count, thumbnail, and broadcaster
    identity via Twitch Helix API.

    Reuses a cached app access token (valid ~60 days); only fetches a new
    token when the cached one is missing or within 5 min of expiry.
    ``creator_id``/``creator_name`` are the clip's ``broadcaster_id``/
    ``broadcaster_name`` (the channel the clip is *of*), not Helix's separate
    ``creator_id``/``creator_name`` (whoever clipped it) — blocking "this
    streamer's clips" is the moderation intent, not "clips this one viewer
    made". All fields are None on any failure.
    """
    if not client_id or not client_secret:
        return TwitchMediaInfo()

    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        app_token = await _get_twitch_app_token(client_id, client_secret, _session)
        if not app_token:
            return TwitchMediaInfo()

        status, data = await _twitch_helix_json(
            _session,
            _TWITCH_HELIX_CLIPS_URL,
            params={"id": slug},
            client_id=client_id,
            token=app_token,
        )
        if status != 200:
            LOGGER.info("[Twitch API] Unexpected status %s for clip %s", status, slug)
            return TwitchMediaInfo()
        clips = data.get("data", [])
        if not clips:
            return TwitchMediaInfo()  # clip not found or deleted
        clip = clips[0]
        title: str | None = clip.get("title")
        duration_raw = clip.get("duration")
        duration_seconds = int(round(float(duration_raw))) if duration_raw is not None else None
        view_count_raw = clip.get("view_count")
        view_count = int(view_count_raw) if view_count_raw is not None else None
        return TwitchMediaInfo(
            title=title,
            duration_seconds=duration_seconds,
            view_count=view_count,
            thumbnail_url=_https(clip.get("thumbnail_url")),
            creator_id=clip.get("broadcaster_id"),
            creator_name=clip.get("broadcaster_name"),
        )
    except Exception as exc:
        LOGGER.warning(
            "[Twitch API] fetch_twitch_clip_info failed for %s: %s", slug, type(exc).__name__
        )
        return TwitchMediaInfo()
    finally:
        if _own_session:
            await _session.close()


async def fetch_twitch_vod_info(
    video_id: str,
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession | None = None,
) -> TwitchMediaInfo:
    """Fetch VOD title, duration, view count, thumbnail, and broadcaster
    identity via Twitch Helix `/videos`.

    ``creator_id``/``creator_name`` are the VOD's ``user_id``/``user_name``
    (the broadcaster). Duration is the full VOD length, not the capped play
    window (the registry applies the cap). All fields are None on failure
    (deleted / sub-only / expired VOD).
    """
    if not client_id or not client_secret:
        return TwitchMediaInfo()

    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        app_token = await _get_twitch_app_token(client_id, client_secret, _session)
        if not app_token:
            return TwitchMediaInfo()

        status, data = await _twitch_helix_json(
            _session,
            _TWITCH_HELIX_VIDEOS_URL,
            params={"id": video_id},
            client_id=client_id,
            token=app_token,
        )
        if status != 200:
            LOGGER.info("[Twitch API] Unexpected status %s for VOD %s", status, video_id)
            return TwitchMediaInfo()
        videos = data.get("data", [])
        if not videos:
            return TwitchMediaInfo()
        vod = videos[0]
        title: str | None = vod.get("title")
        raw_duration: str | None = vod.get("duration")  # "3h20m5s"
        duration_seconds = _parse_hms(raw_duration) if raw_duration else None
        view_count_raw = vod.get("view_count")
        view_count = int(view_count_raw) if view_count_raw is not None else None
        # thumbnail_url has %{width}x%{height} placeholders; empty while the
        # VOD is still processing.
        raw_thumb: str = vod.get("thumbnail_url") or ""
        thumb = (
            raw_thumb.replace("%{width}", "320").replace("%{height}", "180")
            if "%{width}" in raw_thumb
            else (raw_thumb or None)
        )
        return TwitchMediaInfo(
            title=title,
            duration_seconds=duration_seconds or None,
            view_count=view_count,
            thumbnail_url=thumb,
            creator_id=vod.get("user_id"),
            creator_name=vod.get("user_name"),
        )
    except Exception as exc:
        LOGGER.warning(
            "[Twitch API] fetch_twitch_vod_info failed for %s: %s", video_id, type(exc).__name__
        )
        return TwitchMediaInfo()
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Twitch clip DIRECT SOURCE — unofficial GraphQL (Bilibili-tier dependency)
# ---------------------------------------------------------------------------
#
# The official `clips.twitch.tv/embed` iframe cannot autoplay inside an OBS
# Browser Source: Twitch's player gates unmuted autoplay on document
# visibility, and OBS renders the page "hidden" (see
# video-queue-platforms.md). The only way to autoplay a clip with sound in OBS
# is to play its MP4 in a host-controlled <video> — but Twitch stopped serving
# a plain MP4 off the thumbnail_url, so the URL now needs a signed token from
# Twitch's PRIVATE GraphQL endpoint (the exact call yt-dlp makes).
#
# This is a second unofficial dependency of the same class as Bilibili's
# metadata endpoint: no SLA, no rate-limit contract. Specifically:
#   - `_TWITCH_GQL_CLIENT_ID` is yt-dlp's registered public client id (it ships
#     in every yt-dlp install; it is NOT a secret and NOT ours).
#   - `_TWITCH_CLIP_SOURCE_HASH` is a persisted-query hash Twitch ROTATES.
#     When it changes this call 400s and callers fall back to the iframe.
#     Keep it in sync with yt-dlp's `_OPERATION_HASHES['ShareClipRenderStatus']`.
#   - The returned token carries an `expires` claim (hours). Resolve it fresh
#     at playback time; never store it.
_TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
_TWITCH_GQL_CLIENT_ID = "ue6666qo983tsx6so1t0vnawi233wa"
_TWITCH_CLIP_SOURCE_HASH = "2db6a3b20eabf510bd3cf465ae2408834b59eb6b8af89ca73ab1486cacecfb63"


async def fetch_twitch_clip_source(
    slug: str,
    session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Resolve a Twitch clip slug to a directly-playable, signed MP4 URL.

    UNOFFICIAL — see the module comment above. Returns the highest-quality
    landscape source with the playback signature appended, or None on any
    failure (callers must fall back to the clips.twitch.tv/embed iframe).
    """
    body = [
        {
            "operationName": "ShareClipRenderStatus",
            "variables": {"slug": slug},
            "extensions": {
                "persistedQuery": {"version": 1, "sha256Hash": _TWITCH_CLIP_SOURCE_HASH}
            },
        }
    ]
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.post(
            _TWITCH_GQL_URL,
            data=json.dumps(body),
            headers={
                "Client-ID": _TWITCH_GQL_CLIENT_ID,
                "Content-Type": "text/plain;charset=UTF-8",
            },
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                LOGGER.warning("[Twitch GQL] clip source status %s for %s", resp.status, slug)
                return None
            data = await resp.json(content_type=None)

        clip = (data[0] if isinstance(data, list) and data else {}).get("data", {}).get("clip")
        if not clip:
            return None
        token = clip.get("playbackAccessToken") or {}
        signature, value = token.get("signature"), token.get("value")
        if not signature or not value:
            return None
        assets = clip.get("assets") or []
        qualities = (assets[0].get("videoQualities") if assets else None) or []
        # videoQualities is ordered highest→lowest resolution.
        source_url = next((q["sourceURL"] for q in qualities if q.get("sourceURL")), None)
        if not source_url:
            return None
        sep = "&" if "?" in source_url else "?"
        return f"{source_url}{sep}sig={signature}&token={quote(value, safe='')}"
    except Exception as exc:
        LOGGER.warning(
            "[Twitch GQL] fetch_twitch_clip_source failed for %s: %s", slug, type(exc).__name__
        )
        return None
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Registry — resolves a URL to a platform, then fetches metadata in one shape
# ---------------------------------------------------------------------------
#
# Three call sites (chat !vq, channel-points redemption, dashboard add) all
# need "figure out which platform this URL is, then fetch its metadata" and
# previously duplicated that cascade inline. This layer composes the
# platform-specific functions above behind one shape so the cascade lives in
# exactly one place. The platform-specific functions themselves are untouched
# — they're already covered by tests and used directly where only one step
# (e.g. just URL parsing) is needed.

type VideoType = Literal["youtube", "twitch_clip", "twitch_vod", "bilibili", "instagram_reel"]


_WATCH_URL_BUILDERS: dict[str, str] = {
    "youtube": "https://youtu.be/{video_id}",
    "twitch_clip": "https://clips.twitch.tv/{video_id}",
    "twitch_vod": "https://www.twitch.tv/videos/{video_id}",
    "bilibili": "https://www.bilibili.com/video/{video_id}",
    "instagram_reel": "https://www.instagram.com/reel/{video_id}/",
}


@dataclass
class ResolvedVideo:
    """A URL identified as belonging to a platform, with its platform-native ID."""

    video_type: VideoType
    video_id: str
    is_vertical: bool = False  # URL-shape hint (e.g. YouTube Shorts); refined by metadata
    start_seconds: int = 0  # twitch_vod `?t=` offset; 0 for everything else


@dataclass
class VideoMetadata:
    """Metadata fetch result, normalized to one shape across all platforms.

    ``playable`` / ``unplayable_reason`` are mostly YouTube signals (see
    ``YouTubeInfo``); Twitch VOD (``UNPLAYABLE_INVALID_TIMESTAMP``), Bilibili
    (``UNPLAYABLE_INVALID_PAGE``), and Instagram (``UNPLAYABLE_NOT_VIDEO``) each
    add one submission-time-only reason of their own. Twitch Clip is always
    reported playable.

    ``metadata_best_effort`` is ``True`` when the values came from an unofficial
    endpoint that datacenter IPs frequently cannot reach (Bilibili, risk-control
    ``-412``). A ``None`` field from such a platform means "could not fetch", not
    "genuinely absent", and it is not something the requester can retry into
    existence — so submission gates that need a missing value skip themselves
    instead of rejecting. Official-API platforms leave this ``False``: a ``None``
    there is a transient failure worth a "try again later".
    """

    title: str | None
    duration_seconds: int | None
    view_count: int | None
    is_vertical: bool
    playable: bool = True
    unplayable_reason: str | None = None
    metadata_best_effort: bool = False
    thumbnail_url: str | None = None
    creator_id: str | None = None
    creator_name: str | None = None


def metadata_gate_unverifiable(value: int | None, *, best_effort: bool) -> bool:
    """Whether a submission gate that needs ``value`` must reject for lack of it.

    ``True`` only when the value is missing *and* the platform's metadata is
    authoritative (a transient fetch failure — tell the requester to retry).
    Best-effort platforms (Bilibili) return ``False``: the gate is skipped
    rather than blocking a submission that could never satisfy it. A present
    value always returns ``False`` — the caller then applies the real check.
    """
    return value is None and not best_effort


async def resolve_video_url(
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
) -> ResolvedVideo | None:
    """Identify which platform a URL belongs to and extract its native ID.

    Tries YouTube, then Twitch Clip, then Twitch VOD, then Instagram Reel,
    then Bilibili (incl. b23.tv redirects) — same priority order previously
    duplicated across call sites. Returns None if the URL doesn't match any
    supported platform.
    """
    video_id, is_vertical = extract_youtube_info(url)
    if video_id:
        return ResolvedVideo(video_type="youtube", video_id=video_id, is_vertical=is_vertical)

    clip_slug = extract_twitch_clip_slug(url)
    if clip_slug:
        return ResolvedVideo(video_type="twitch_clip", video_id=clip_slug)

    vod_id, start_seconds = extract_twitch_vod_info(url)
    if vod_id:
        return ResolvedVideo(video_type="twitch_vod", video_id=vod_id, start_seconds=start_seconds)

    # ResolvedVideo has no is_vertical hint for Instagram (unlike YouTube's
    # Shorts URL shape) — the real value comes from fetch_video_metadata()'s
    # instagram_reel branch, which detects it from the OG page's dimensions
    # when present, else a probe of the resolved mp4's own container (see
    # instafix_client._orientation_from_og / _orientation_from_mp4).
    shortcode = await resolve_instagram_url(url, session)
    if shortcode:
        return ResolvedVideo(video_type="instagram_reel", video_id=shortcode)

    bvid = await resolve_bilibili_url(url, session)
    if bvid:
        return ResolvedVideo(video_type="bilibili", video_id=bvid)

    return None


async def fetch_video_metadata(
    resolved: ResolvedVideo,
    *,
    youtube_api_key: str = "",
    twitch_client_id: str = "",
    twitch_client_secret: str = "",
    instafix_host: str = "instafix:3000",
    session: aiohttp.ClientSession | None = None,
) -> VideoMetadata:
    """Fetch metadata for a resolved video, normalized to one shape.

    Twitch Clip's underlying fetch has no is_vertical concept (Helix doesn't
    report clip dimensions) — normalized to False here rather than making
    every caller remember to supply it.
    """
    if resolved.video_type == "twitch_clip":
        clip = await fetch_twitch_clip_info(
            resolved.video_id, twitch_client_id, twitch_client_secret, session
        )
        return VideoMetadata(
            clip.title,
            clip.duration_seconds,
            clip.view_count,
            is_vertical=False,
            thumbnail_url=clip.thumbnail_url,
            creator_id=clip.creator_id,
            creator_name=clip.creator_name,
        )

    if resolved.video_type == "twitch_vod":
        vod = await fetch_twitch_vod_info(
            resolved.video_id, twitch_client_id, twitch_client_secret, session
        )
        if vod.duration_seconds and resolved.start_seconds >= vod.duration_seconds:
            return VideoMetadata(
                vod.title,
                0,
                vod.view_count,
                is_vertical=False,
                playable=False,
                unplayable_reason=UNPLAYABLE_INVALID_TIMESTAMP,
                thumbnail_url=vod.thumbnail_url,
                creator_id=vod.creator_id,
                creator_name=vod.creator_name,
            )
        # Play a bounded window from the `?t=` offset — a VOD is hours long.
        remaining = (
            max(0, vod.duration_seconds - resolved.start_seconds)
            if vod.duration_seconds
            else TWITCH_VOD_WINDOW_SECONDS
        )
        window = min(TWITCH_VOD_WINDOW_SECONDS, remaining) or TWITCH_VOD_WINDOW_SECONDS
        return VideoMetadata(
            vod.title,
            window,
            vod.view_count,
            is_vertical=False,
            thumbnail_url=vod.thumbnail_url,
            creator_id=vod.creator_id,
            creator_name=vod.creator_name,
        )

    if resolved.video_type == "bilibili":
        bvid, page = split_bilibili_id(resolved.video_id)
        bili = await fetch_bilibili_info(bvid, session, page=page)
        # page_count is only known when the view endpoint actually answered
        # (not risk-controlled) — reject a part number past the end only when
        # that's positively established, same "only a positive signal
        # rejects" convention as YouTube's playability checks.
        if bili.page_count is not None and page > bili.page_count:
            return VideoMetadata(
                bili.title,
                0,
                bili.view_count,
                bili.is_vertical,
                playable=False,
                unplayable_reason=UNPLAYABLE_INVALID_PAGE,
                metadata_best_effort=True,
                thumbnail_url=bili.thumbnail_url,
                creator_id=bili.creator_id,
                creator_name=bili.creator_name,
            )
        return VideoMetadata(
            bili.title,
            bili.duration_seconds,
            bili.view_count,
            bili.is_vertical,
            metadata_best_effort=True,
            thumbnail_url=bili.thumbnail_url,
            creator_id=bili.creator_id,
            creator_name=bili.creator_name,
        )

    if resolved.video_type == "instagram_reel":
        reel_info = await fetch_instagram_reel_info(resolved.video_id, instafix_host, session)
        # view_count is permanently unavailable from InstaFix's OG data —
        # metadata_best_effort=True keeps the min_view_count gate skipping
        # rather than rejecting an unwinnable submission. duration_seconds
        # *is* usually available now (see shared.instafix_client's
        # _extract_duration_seconds — rides along in the same video redirect
        # fetch_instagram_reel_source() resolves at play time); when it
        # isn't (that redirect failed), it falls back to the same
        # reportVideoMetadata client-side backfill Twitch Clip uses.
        # Most Reels are 9:16, but a landscape source video keeps its own
        # aspect ratio when posted as a Reel — reel_info.is_vertical tries
        # the OG page's og:video:width/height first (rarely present in
        # practice), then a probe of the resolved mp4's own container
        # dimensions, defaulting True only if both fail (see
        # instafix_client._orientation_from_og / _orientation_from_mp4).
        # Only when True does the overlay give it the blurred-side-column
        # treatment, same as a YouTube Short (players/instagramReel.ts mounts
        # two extra <video> elements, not YT.Player instances, into the same
        # left/right containers).
        #
        # is_video is only ever positively False for a `/p/` link whose video
        # redirect resolved to a non-mp4 target (a photo post) — a redirect
        # that merely failed to resolve leaves it None/unknown and is not
        # rejected here (same "only a positive signal rejects" convention as
        # YouTube's playability checks).
        if reel_info.is_video is False:
            return VideoMetadata(
                title=reel_info.title,
                duration_seconds=0,
                view_count=None,
                is_vertical=reel_info.is_vertical,
                playable=False,
                unplayable_reason=UNPLAYABLE_NOT_VIDEO,
                metadata_best_effort=True,
                thumbnail_url=reel_info.thumbnail_url,
                creator_id=reel_info.creator_id,
                creator_name=reel_info.creator_name,
            )
        return VideoMetadata(
            title=reel_info.title,
            duration_seconds=reel_info.duration_seconds,
            view_count=None,
            is_vertical=reel_info.is_vertical,
            metadata_best_effort=True,
            thumbnail_url=reel_info.thumbnail_url,
            creator_id=reel_info.creator_id,
            creator_name=reel_info.creator_name,
        )

    yt = await fetch_yt_info(resolved.video_id, youtube_api_key, session)
    return VideoMetadata(
        title=yt.title,
        duration_seconds=yt.duration_seconds,
        view_count=yt.view_count,
        is_vertical=resolved.is_vertical or yt.is_vertical,
        playable=yt.playable,
        unplayable_reason=yt.unplayable_reason,
        thumbnail_url=yt.thumbnail_url,
        creator_id=yt.creator_id,
        creator_name=yt.creator_name,
    )


def build_watch_url(video_type: str, video_id: str, start_seconds: int = 0) -> str:
    """Build the canonical watch URL for a queued entry, given its stored video_type."""
    template = _WATCH_URL_BUILDERS.get(video_type)
    if template is None:
        raise ValueError(f"Unknown video_type: {video_type!r}")
    if video_type == "bilibili":
        bvid, page = split_bilibili_id(video_id)
        url = template.format(video_id=bvid)
        return f"{url}?p={page}" if page > 1 else url
    url = template.format(video_id=video_id)
    if video_type == "twitch_vod" and start_seconds > 0:
        return f"{url}?t={start_seconds}s"
    return url
