"""Constants for the social preview cog."""

import os
import re

# ── URL patterns ──────────────────────────────────────────────────────────────

INSTAGRAM_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(p|reel|tv)/([A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)

THREADS_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/@?[\w.]+/post/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

BILIBILI_RE = re.compile(
    r"https?://(?:(?:www\.)?bilibili\.com/video/(BV[A-Za-z0-9]+)"
    r"|b23\.tv/([A-Za-z0-9]+))",
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
TIKTOK_OEMBED_API = "https://www.tiktok.com/oembed?url={url}"

# Self-hosted InstaFix (github.com/Wikidepia/InstaFix).
# Docker: "instafix:3000" (niibot-network) | Local dev: "localhost:3000"
INSTAFIX_HOST = os.getenv("INSTAFIX_HOST", "instafix:3000")
INSTAGRAM_PROXY_URL = "http://{host}/{path}/{shortcode}/"
INSTAGRAM_ICON_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png"

# ── Colours ───────────────────────────────────────────────────────────────────

COLOR_INSTAGRAM = 0xE1306C
COLOR_THREADS = 0x101010
COLOR_BILIBILI = 0x00A1D6
COLOR_TIKTOK = 0x010101

# ── Misc ──────────────────────────────────────────────────────────────────────

HTTP_TIMEOUT = 10.0
DESCRIPTION_LIMIT = 300
DISMISS_TIMEOUT = 120.0  # seconds before ✕ button is removed
