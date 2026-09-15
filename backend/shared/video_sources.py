"""Video source utilities: URL parsing + metadata fetching.

Split out of ``shared.repositories.video_queue`` — these helpers do pure string
parsing and public-API calls, with no database dependency. Used by the Twitch
bot, channel-points redemptions, and the donation webhook.

  - extract_youtube_id / extract_youtube_info : pure YouTube URL parsing
  - fetch_yt_info                              : YouTube Data API v3 call
  - extract_bilibili_bvid / resolve_bilibili_url : Bilibili BV parsing (+ b23.tv)
  - fetch_bilibili_info                        : Bilibili metadata (via
    shared.bilibili_client — three risk-control-aware tiers)
  - extract_twitch_clip_slug                   : Twitch clip URL parsing
  - fetch_twitch_clip_info                     : Twitch Helix clips API call

  - resolve_video_url / fetch_video_metadata / build_watch_url : registry
    layer composing the platform-specific functions above behind one shape,
    for callers that just want "figure out what this URL is and fetch its
    metadata" without repeating the per-platform cascade themselves.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

from shared.bilibili_client import fetch_bilibili_video_data

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

# Playability reasons the OBS overlay cannot recover from — the iframe either
# refuses to embed or silently shows an error, and the queue only advances once
# the timer ceiling expires. Reject these at submission instead. YouTube-only:
# Twitch clips always embed, and Bilibili's metadata endpoint is too unreliable
# to gate on (see docs/architecture/video-queue-platforms.md).
UNPLAYABLE_NOT_EMBEDDABLE = "not_embeddable"
UNPLAYABLE_AGE_RESTRICTED = "age_restricted"
UNPLAYABLE_PRIVATE = "private"
UNPLAYABLE_REMOVED = "removed"

_UNPLAYABLE_MESSAGES: dict[str, str] = {
    UNPLAYABLE_NOT_EMBEDDABLE: "這部影片不開放外部播放",
    UNPLAYABLE_AGE_RESTRICTED: "這部影片有年齡限制，無法播放",
    UNPLAYABLE_PRIVATE: "這是私人影片，無法播放",
    UNPLAYABLE_REMOVED: "這部影片已被移除或無法使用",
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
) -> tuple[str | None, int | None, int | None, bool, str | None]:
    """Fetch title, duration, view count, orientation, and cover image from Bilibili.

    Returns ``(title, duration_seconds, view_count, is_vertical, thumbnail_url)``.
    All values are None/False when every tier of :mod:`shared.bilibili_client` is
    blocked or the video is unavailable — Bilibili has no official metadata API
    and a datacenter IP is often risk-controlled, so callers must treat this as
    "unknown", not "reject" (see ``metadata_best_effort`` on :class:`VideoMetadata`).
    """
    data = await fetch_bilibili_video_data(bvid, session=session)
    if not data:
        return None, None, None, False, None
    title: str | None = data.get("title")
    duration_seconds: int | None = data.get("duration")
    view_count_raw = (data.get("stat") or {}).get("view")
    view_count: int | None = int(view_count_raw) if view_count_raw is not None else None
    dimension = data.get("dimension") or {}
    width = dimension.get("width") or 0
    height = dimension.get("height") or 0
    is_vertical = height > width if width > 0 and height > 0 else False
    return title, duration_seconds, view_count, is_vertical, _https(data.get("pic"))


# ---------------------------------------------------------------------------
# Twitch Clip utilities
# ---------------------------------------------------------------------------


_TWITCH_CLIP_RE = re.compile(
    r"(?:https?://)?(?:clips\.twitch\.tv/|www\.twitch\.tv/\w+/clip/)([A-Za-z0-9_-]+)"
)

_TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
_TWITCH_HELIX_CLIPS_URL = "https://api.twitch.tv/helix/clips"
_TWITCH_HELIX_VIDEOS_URL = "https://api.twitch.tv/helix/videos"

# twitch.tv/videos/{id} (also m.twitch.tv). The id is numeric.
_TWITCH_VOD_RE = re.compile(r"(?:https?://)?(?:www\.|m\.)?twitch\.tv/videos/(\d+)")
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


def extract_twitch_clip_slug(text: str) -> str | None:
    """Extract clip slug from a Twitch clip URL. Returns None if not found.

    Supports:
      - https://clips.twitch.tv/{slug}
      - https://www.twitch.tv/{channel}/clip/{slug}
    """
    m = _TWITCH_CLIP_RE.search(text)
    return m.group(1) if m else None


def extract_twitch_vod_info(text: str) -> tuple[str | None, int]:
    """Extract a Twitch VOD id and its `?t=` start offset (seconds).

    Returns (video_id, start_seconds); video_id is None if the URL isn't a
    twitch.tv/videos/{id} link. start_seconds defaults to 0.
    """
    m = _TWITCH_VOD_RE.search(text)
    if not m:
        return None, 0
    t_match = re.search(r"[?&]t=([0-9hms]+)", text, re.IGNORECASE)
    return m.group(1), _parse_hms(t_match.group(1)) if t_match else 0


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
) -> tuple[str | None, int | None, int | None, str | None]:
    """Fetch clip title, duration, view count, and thumbnail via Twitch Helix API.

    Reuses a cached app access token (valid ~60 days); only fetches a new
    token when the cached one is missing or within 5 min of expiry.
    Returns (title, duration_seconds, view_count, thumbnail_url).
    All values are None on any failure.
    """
    if not client_id or not client_secret:
        return None, None, None, None

    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        app_token = await _get_twitch_app_token(client_id, client_secret, _session)
        if not app_token:
            return None, None, None, None

        # Fetch clip metadata
        async with _session.get(
            _TWITCH_HELIX_CLIPS_URL,
            params={"id": slug},
            headers={"Authorization": f"Bearer {app_token}", "Client-Id": client_id},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                LOGGER.info("[Twitch API] Unexpected status %s for clip %s", resp.status, slug)
                return None, None, None, None
            data = await resp.json()
            clips = data.get("data", [])
            if not clips:
                return None, None, None, None  # clip not found or deleted
            clip = clips[0]
            title: str | None = clip.get("title")
            duration_raw = clip.get("duration")
            duration_seconds = int(round(float(duration_raw))) if duration_raw is not None else None
            view_count_raw = clip.get("view_count")
            view_count = int(view_count_raw) if view_count_raw is not None else None
            return title, duration_seconds, view_count, _https(clip.get("thumbnail_url"))
    except Exception as exc:
        LOGGER.warning(
            "[Twitch API] fetch_twitch_clip_info failed for %s: %s", slug, type(exc).__name__
        )
        return None, None, None, None
    finally:
        if _own_session:
            await _session.close()


async def fetch_twitch_vod_info(
    video_id: str,
    client_id: str,
    client_secret: str,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, int | None, int | None, str | None]:
    """Fetch VOD title, duration, view count, and thumbnail via Twitch Helix `/videos`.

    Returns (title, duration_seconds, view_count, thumbnail_url) — the full VOD
    duration, not the capped play window (the registry applies the cap). All None
    on failure (deleted / sub-only / expired VOD).
    """
    if not client_id or not client_secret:
        return None, None, None, None

    _own_session = session is None
    _session: aiohttp.ClientSession = session or aiohttp.ClientSession()
    try:
        app_token = await _get_twitch_app_token(client_id, client_secret, _session)
        if not app_token:
            return None, None, None, None

        async with _session.get(
            _TWITCH_HELIX_VIDEOS_URL,
            params={"id": video_id},
            headers={"Authorization": f"Bearer {app_token}", "Client-Id": client_id},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                LOGGER.info("[Twitch API] Unexpected status %s for VOD %s", resp.status, video_id)
                return None, None, None, None
            data = await resp.json()
            videos = data.get("data", [])
            if not videos:
                return None, None, None, None
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
            return title, duration_seconds or None, view_count, thumb
    except Exception as exc:
        LOGGER.warning(
            "[Twitch API] fetch_twitch_vod_info failed for %s: %s", video_id, type(exc).__name__
        )
        return None, None, None, None
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

_WATCH_URL_BUILDERS: dict[str, str] = {
    "youtube": "https://youtu.be/{video_id}",
    "twitch_clip": "https://clips.twitch.tv/{video_id}",
    "twitch_vod": "https://www.twitch.tv/videos/{video_id}",
    "bilibili": "https://www.bilibili.com/video/{video_id}",
}


@dataclass
class ResolvedVideo:
    """A URL identified as belonging to a platform, with its platform-native ID."""

    video_type: str  # 'youtube' | 'twitch_clip' | 'twitch_vod' | 'bilibili'
    video_id: str
    is_vertical: bool = False  # URL-shape hint (e.g. YouTube Shorts); refined by metadata
    start_seconds: int = 0  # twitch_vod `?t=` offset; 0 for everything else


@dataclass
class VideoMetadata:
    """Metadata fetch result, normalized to one shape across all platforms.

    ``playable`` / ``unplayable_reason`` are YouTube-only signals (see
    ``YouTubeInfo``); Twitch Clip and Bilibili are always reported playable.

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

    vod_id, start_seconds = extract_twitch_vod_info(url)
    if vod_id:
        return ResolvedVideo(video_type="twitch_vod", video_id=vod_id, start_seconds=start_seconds)

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
        title, duration_seconds, view_count, thumbnail_url = await fetch_twitch_clip_info(
            resolved.video_id, twitch_client_id, twitch_client_secret, session
        )
        return VideoMetadata(
            title, duration_seconds, view_count, is_vertical=False, thumbnail_url=thumbnail_url
        )

    if resolved.video_type == "twitch_vod":
        title, vod_duration, view_count, thumbnail_url = await fetch_twitch_vod_info(
            resolved.video_id, twitch_client_id, twitch_client_secret, session
        )
        # Play a bounded window from the `?t=` offset — a VOD is hours long.
        remaining = (
            max(0, vod_duration - resolved.start_seconds)
            if vod_duration
            else TWITCH_VOD_WINDOW_SECONDS
        )
        window = min(TWITCH_VOD_WINDOW_SECONDS, remaining) or TWITCH_VOD_WINDOW_SECONDS
        return VideoMetadata(
            title, window, view_count, is_vertical=False, thumbnail_url=thumbnail_url
        )

    if resolved.video_type == "bilibili":
        title, duration_seconds, view_count, is_vertical, thumbnail_url = await fetch_bilibili_info(
            resolved.video_id, session
        )
        return VideoMetadata(
            title,
            duration_seconds,
            view_count,
            is_vertical,
            metadata_best_effort=True,
            thumbnail_url=thumbnail_url,
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
    )


def build_watch_url(video_type: str, video_id: str) -> str:
    """Build the canonical watch URL for a queued entry, given its stored video_type."""
    template = _WATCH_URL_BUILDERS.get(video_type)
    if template is None:
        raise ValueError(f"Unknown video_type: {video_type!r}")
    return template.format(video_id=video_id)
