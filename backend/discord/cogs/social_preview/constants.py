"""Constants for the social preview cog."""

import re

# ── URL patterns ──────────────────────────────────────────────────────────────
#
# X / Twitter  — excluded, Discord native embed is sufficient
# YouTube      — excluded, Discord native embed is sufficient
# Facebook     — excluded, no viable server-side scraping solution (JS login wall)
# 小紅書        — excluded, requires maintained cookie session (7-day expiry)

INSTAGRAM_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?",
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

# Instagram proxy — InstaFix (github.com/Wikidepia/InstaFix)
# Replaces instagram.com with ddinstagram.com; returns static HTML with OG tags.
DDINSTAGRAM_HOST = "www.ddinstagram.com"

# ── Colours ───────────────────────────────────────────────────────────────────

COLOR_INSTAGRAM = 0xE1306C
COLOR_THREADS = 0x101010
COLOR_BILIBILI = 0x00A1D6
COLOR_TIKTOK = 0x010101

# ── Misc ──────────────────────────────────────────────────────────────────────

HTTP_TIMEOUT = 10.0
DESCRIPTION_LIMIT = 300
