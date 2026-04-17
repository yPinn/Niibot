"""Constants for the social preview cog."""

import re

from core.config import get_settings as _get_settings

# ── URL patterns ──────────────────────────────────────────────────────────────

_IG_HOST = r"(?:(?:www\.|m\.)?instagram\.com|(?:www\.)?instagr\.am)"

INSTAGRAM_RE = re.compile(
    rf"https?://{_IG_HOST}/(p|reel|tv)/([A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)

# Matches profile pages (e.g. instagram.com/tp.y__/) but not post/reel/tv/stories/… paths.
# Trailing lookahead prevents matching sub-paths (e.g. /stories/username/…).
INSTAGRAM_PROFILE_RE = re.compile(
    r"https?://(?:www\.|m\.)?instagram\.com/"
    r"(?!(?:p|reel|tv|stories|explore|accounts|direct|api|tags|locations|login)(?:/|\?|\s|$))"
    r"([A-Za-z0-9_.]{1,30})(?=/?(?:\?|\s|$))",
    re.IGNORECASE,
)

THREADS_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/@?[\w.]+/post/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

BILIBILI_RE = re.compile(
    r"https?://(?:(?:www\.|m\.)?bilibili\.com/video/(BV[A-Za-z0-9]+)"
    r"|b23\.tv/([A-Za-z0-9]+))",
    re.IGNORECASE,
)

BILIBILI_SPACE_RE = re.compile(
    r"https?://space\.bilibili\.com/(\d+)",
    re.IGNORECASE,
)

TIKTOK_RE = re.compile(
    r"https?://(?:"
    r"(?:www\.)?tiktok\.com/@[\w.]+/video/\d+"
    r"|vm\.tiktok\.com/[A-Za-z0-9]+"
    r"|vt\.tiktok\.com/[A-Za-z0-9]+"
    r")/?",
    re.IGNORECASE,
)

# ── External APIs ─────────────────────────────────────────────────────────────

BILIBILI_API = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
BILIBILI_CARD_API = "https://api.bilibili.com/x/web-interface/card?mid={mid}"
BILIBILI_SPACE_URL = "https://space.bilibili.com/{mid}"
TIKTOK_OEMBED_API = "https://www.tiktok.com/oembed?url={url}"

# Instagram internal web API. Unauthenticated requests 429 quickly;
# set INSTAGRAM_SESSION_ID in .env to inject a sessionid cookie.
INSTAGRAM_PROFILE_API = (
    "https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
)
INSTAGRAM_APP_ID = "936619743392459"

# Self-hosted InstaFix (github.com/Wikidepia/InstaFix).
# Docker: "instafix:3000" | Local dev: "localhost:3000"
INSTAFIX_HOST = _get_settings().instafix_host
INSTAGRAM_PROXY_URL = "http://{host}/{path}/{shortcode}/"
INSTAGRAM_ICON_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png"

# ── Colours ───────────────────────────────────────────────────────────────────

COLOR_INSTAGRAM = 0xE1306C
COLOR_THREADS = 0x101010
COLOR_BILIBILI = 0x00A1D6
COLOR_TIKTOK = 0x010101

# ── Misc ──────────────────────────────────────────────────────────────────────

HTTP_TIMEOUT = 10.0
DESCRIPTION_LIMIT = 4096  # Discord embed description hard limit — do not lower
DISMISS_TIMEOUT = 120.0
VIDEO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB — Discord Level 1 Boost upload limit
