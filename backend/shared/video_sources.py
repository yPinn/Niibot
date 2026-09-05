"""Video source utilities: URL parsing + metadata fetching.

Split out of ``shared.repositories.video_queue`` — these helpers do pure string
parsing and public-API calls, with no database dependency. Used by the Twitch
bot, channel-points redemptions, and the donation webhook.

  - extract_youtube_id / extract_youtube_info : pure YouTube URL parsing
  - fetch_yt_info                              : YouTube Data API v3 call
  - extract_bilibili_bvid / resolve_bilibili_url : Bilibili BV parsing (+ b23.tv)
  - fetch_bilibili_info                        : Bilibili public API call
  - extract_twitch_clip_slug                   : Twitch clip URL parsing
  - fetch_twitch_clip_info                     : Twitch Helix clips API call

  - resolve_video_url / fetch_video_metadata / build_watch_url : registry
    layer composing the platform-specific functions above behind one shape,
    for callers that just want "figure out what this URL is and fetch its
    metadata" without repeating the per-platform cascade themselves.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import aiohttp

LOGGER: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YouTube utilities
# ---------------------------------------------------------------------------

_YT_SHORTS_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})")

_YT_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:"
    r"youtube\.com/watch\?(?:.*&)?v=|"
    r"youtu\.be/|"
    r"youtube\.com/shorts/"
    r")([A-Za-z0-9_-]{11})"
)

_ISO8601_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def extract_youtube_id(text: str) -> str | None:
    """Extract 11-char YouTube video ID from a URL string. Returns None if not found."""
    m = _YT_RE.search(text)
    return m.group(1) if m else None


def extract_youtube_info(text: str) -> tuple[str | None, bool]:
    """Extract YouTube video ID and whether the URL is a Short (vertical video).

    Returns:
        (video_id, is_vertical) — video_id is None if no match found.
    """
    if _YT_SHORTS_RE.search(text):
        m = _YT_RE.search(text)
        return (m.group(1) if m else None, True)
    m = _YT_RE.search(text)
    return (m.group(1) if m else None, False)


def _parse_iso8601_duration(duration: str) -> int:
    """Parse ISO 8601 duration (e.g. 'PT1H3M45S') to total seconds."""
    m = _ISO8601_RE.match(duration)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


async def fetch_yt_info(
    video_id: str,
    api_key: str,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, int | None, int | None, bool]:
    """Fetch video title, duration, view count, and orientation via YouTube Data API v3.

    If `session` is None a temporary one-shot session is created and closed.
    Returns (title, duration_seconds, view_count, is_vertical).
    is_vertical is True when the API reports portrait thumbnails (e.g. YouTube Shorts).
    title/duration/view_count are None on any failure; is_vertical defaults to False.
    """
    if not api_key:
        return None, None, None, False

    url = "https://www.googleapis.com/youtube/v3/videos"
    # Pass api_key via params dict so it never appears as a literal URL string
    # (prevents accidental key exposure in logs, traces, or error messages).
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": video_id,
        "key": api_key,
    }
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                LOGGER.info("[YouTube API] Unexpected status %s for %s", resp.status, video_id)
                return None, None, None, False
            data = await resp.json()
            items = data.get("items", [])
            if not items:
                return None, None, None, False  # video not found / private
            item = items[0]
            title: str | None = item.get("snippet", {}).get("title")
            raw_duration: str = item.get("contentDetails", {}).get("duration", "")
            duration_seconds = _parse_iso8601_duration(raw_duration) if raw_duration else 0
            raw_views: str | None = item.get("statistics", {}).get("viewCount")
            view_count = int(raw_views) if raw_views else None
            # Detect portrait orientation from thumbnail dimensions (Shorts have h > w)
            thumbnails: dict = item.get("snippet", {}).get("thumbnails", {})
            is_vertical = any(
                (t.get("height", 0) or 0) > (t.get("width", 1) or 1) for t in thumbnails.values()
            )
            return title, duration_seconds or None, view_count, is_vertical
    except Exception as exc:
        LOGGER.warning(
            "[YouTube API] fetch_yt_info failed for %s: %s", video_id, type(exc).__name__
        )
        return None, None, None, False
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Bilibili utilities
# ---------------------------------------------------------------------------

_BILIBILI_BV_RE = re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[A-Za-z0-9]{10})")
_BILIBILI_SHORT_RE = re.compile(r"(?:https?://)?b23\.tv/[A-Za-z0-9]+")


def extract_bilibili_bvid(text: str) -> str | None:
    """Extract Bilibili BV ID from full bilibili.com URL. Returns None if not found."""
    m = _BILIBILI_BV_RE.search(text)
    return m.group(1) if m else None


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

    if not _BILIBILI_SHORT_RE.search(url):
        return None

    full_url = url if url.startswith("http") else f"https://{url}"
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(
            full_url,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=5),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as resp:
            return extract_bilibili_bvid(str(resp.url))
    except Exception as exc:
        LOGGER.warning("[Bilibili] Failed to resolve short URL %s: %s", url, type(exc).__name__)
        return None
    finally:
        if _own_session:
            await _session.close()


async def fetch_bilibili_info(
    bvid: str,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, int | None, int | None, bool]:
    """Fetch video title, duration, view count, and orientation via Bilibili public API.

    Returns (title, duration_seconds, view_count, is_vertical).
    All values are None/False on any failure.
    """
    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        async with _session.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
            headers={
                "Referer": "https://www.bilibili.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                LOGGER.warning("[Bilibili API] Unexpected status %s for %s", resp.status, bvid)
                return None, None, None, False
            data = await resp.json(content_type=None)
            if data.get("code") != 0:
                # code -412 is Bilibili's risk-control block, common from
                # datacenter IPs. The overlay falls back to a timer ceiling
                # (players/shared.ts) so the queue still advances without a
                # duration — but the entry loses accurate timing.
                LOGGER.warning(
                    "[Bilibili API] Error %s for %s: %s",
                    data.get("code"),
                    bvid,
                    data.get("message"),
                )
                return None, None, None, False
            video_data = data.get("data", {})
            title: str | None = video_data.get("title")
            duration_seconds: int | None = video_data.get("duration")
            view_count_raw = video_data.get("stat", {}).get("view")
            view_count: int | None = int(view_count_raw) if view_count_raw is not None else None
            dimension = video_data.get("dimension", {})
            width = dimension.get("width") or 0
            height = dimension.get("height") or 0
            is_vertical = height > width if width > 0 and height > 0 else False
            return title, duration_seconds, view_count, is_vertical
    except Exception as exc:
        LOGGER.warning(
            "[Bilibili API] fetch_bilibili_info failed for %s: %s", bvid, type(exc).__name__
        )
        return None, None, None, False
    finally:
        if _own_session:
            await _session.close()


# ---------------------------------------------------------------------------
# Twitch Clip utilities
# ---------------------------------------------------------------------------


_TWITCH_CLIP_RE = re.compile(
    r"(?:https?://)?(?:clips\.twitch\.tv/|www\.twitch\.tv/\w+/clip/)([A-Za-z0-9_-]+)"
)

_TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
_TWITCH_HELIX_CLIPS_URL = "https://api.twitch.tv/helix/clips"

# Module-level app token cache keyed by (client_id, client_secret).
# Twitch app tokens are valid for ~60 days; we refresh 5 min before expiry.
_app_token_cache: dict[tuple[str, str], tuple[str, float]] = {}  # key → (token, expires_at)


def extract_twitch_clip_slug(text: str) -> str | None:
    """Extract clip slug from a Twitch clip URL. Returns None if not found.

    Supports:
      - https://clips.twitch.tv/{slug}
      - https://www.twitch.tv/{channel}/clip/{slug}
    """
    m = _TWITCH_CLIP_RE.search(text)
    return m.group(1) if m else None


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


async def fetch_twitch_clip_info(
    slug: str,
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, int | None, int | None]:
    """Fetch clip title, duration, and view count via Twitch Helix API.

    Reuses a cached app access token (valid ~60 days); only fetches a new
    token when the cached one is missing or within 5 min of expiry.
    Returns (title, duration_seconds, view_count).
    All values are None on any failure.
    """
    if not client_id or not client_secret:
        return None, None, None

    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        app_token = await _get_twitch_app_token(client_id, client_secret, _session)
        if not app_token:
            return None, None, None

        # Fetch clip metadata
        async with _session.get(
            _TWITCH_HELIX_CLIPS_URL,
            params={"id": slug},
            headers={"Authorization": f"Bearer {app_token}", "Client-Id": client_id},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                LOGGER.info("[Twitch API] Unexpected status %s for clip %s", resp.status, slug)
                return None, None, None
            data = await resp.json()
            clips = data.get("data", [])
            if not clips:
                return None, None, None  # clip not found or deleted
            clip = clips[0]
            title: str | None = clip.get("title")
            duration_raw = clip.get("duration")
            duration_seconds = int(round(float(duration_raw))) if duration_raw is not None else None
            view_count_raw = clip.get("view_count")
            view_count = int(view_count_raw) if view_count_raw is not None else None
            return title, duration_seconds, view_count
    except Exception as exc:
        LOGGER.warning(
            "[Twitch API] fetch_twitch_clip_info failed for %s: %s", slug, type(exc).__name__
        )
        return None, None, None
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

_WATCH_URL_BUILDERS: dict[str, str] = {
    "youtube": "https://youtu.be/{video_id}",
    "twitch_clip": "https://clips.twitch.tv/{video_id}",
    "bilibili": "https://www.bilibili.com/video/{video_id}",
}


@dataclass
class ResolvedVideo:
    """A URL identified as belonging to a platform, with its platform-native ID."""

    video_type: str  # 'youtube' | 'twitch_clip' | 'bilibili'
    video_id: str
    is_vertical: bool = False  # URL-shape hint (e.g. YouTube Shorts); refined by metadata


@dataclass
class VideoMetadata:
    """Metadata fetch result, normalized to one shape across all platforms."""

    title: str | None
    duration_seconds: int | None
    view_count: int | None
    is_vertical: bool


async def resolve_video_url(
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
) -> ResolvedVideo | None:
    """Identify which platform a URL belongs to and extract its native ID.

    Tries YouTube, then Twitch Clip, then Bilibili (incl. b23.tv redirects) —
    same priority order previously duplicated across call sites. Returns None
    if the URL doesn't match any supported platform.
    """
    video_id, is_vertical = extract_youtube_info(url)
    if video_id:
        return ResolvedVideo(video_type="youtube", video_id=video_id, is_vertical=is_vertical)

    clip_slug = extract_twitch_clip_slug(url)
    if clip_slug:
        return ResolvedVideo(video_type="twitch_clip", video_id=clip_slug)

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
    session: aiohttp.ClientSession | None = None,
) -> VideoMetadata:
    """Fetch metadata for a resolved video, normalized to one 4-field shape.

    Twitch Clip's underlying fetch has no is_vertical concept (Helix doesn't
    report clip dimensions) — normalized to False here rather than making
    every caller remember to supply it.
    """
    if resolved.video_type == "twitch_clip":
        title, duration_seconds, view_count = await fetch_twitch_clip_info(
            resolved.video_id, twitch_client_id, twitch_client_secret, session
        )
        return VideoMetadata(title, duration_seconds, view_count, is_vertical=False)

    if resolved.video_type == "bilibili":
        title, duration_seconds, view_count, is_vertical = await fetch_bilibili_info(
            resolved.video_id, session
        )
        return VideoMetadata(title, duration_seconds, view_count, is_vertical)

    title, duration_seconds, view_count, is_vertical_from_api = await fetch_yt_info(
        resolved.video_id, youtube_api_key, session
    )
    return VideoMetadata(
        title, duration_seconds, view_count, resolved.is_vertical or is_vertical_from_api
    )


def build_watch_url(video_type: str, video_id: str) -> str:
    """Build the canonical watch URL for a queued entry, given its stored video_type."""
    template = _WATCH_URL_BUILDERS.get(video_type)
    if template is None:
        raise ValueError(f"Unknown video_type: {video_type!r}")
    return template.format(video_id=video_id)
