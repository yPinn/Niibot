"""Constants for the social preview cog."""

import re

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

# Matches profile pages (e.g. threads.com/@handle). Checked after THREADS_RE so
# post URLs are never captured here.
THREADS_PROFILE_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/@([\w.]+)(?:/?(?:\?[^\s]*)?)?(?=\s|$)",
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

BILIBILI_LIVE_RE = re.compile(
    r"https?://live\.bilibili\.com/(\d+)",
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

TWITCH_CLIP_RE = re.compile(
    r"https?://(?:"
    r"clips\.twitch\.tv/([A-Za-z0-9_-]+)"
    r"|(?:www\.|m\.)?twitch\.tv/(?:\w+/)?clip/([A-Za-z0-9_-]+)"
    r")",
    re.IGNORECASE,
)

# Matches twitch.tv/<username> channel pages. Checked after TWITCH_CLIP_RE so clip URLs
# are never captured here. Negative lookahead excludes known non-channel paths.
TWITCH_CHANNEL_RE = re.compile(
    r"https?://(?:www\.|m\.)?twitch\.tv/"
    r"(?!(?:directory|login|signup|legal|settings|moderator|dashboard|following|friends|inventory|drops|prime|bits|turbo|communities|p)(?:/|\?|\s|$))"
    r"([A-Za-z0-9_]{1,25})(?:/?(?:\?[^\s]*)?)?",
    re.IGNORECASE,
)

# ── External APIs ─────────────────────────────────────────────────────────────

BILIBILI_API = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
BILIBILI_CARD_API = "https://api.bilibili.com/x/web-interface/card?mid={mid}"
BILIBILI_SPACE_URL = "https://space.bilibili.com/{mid}"
BILIBILI_LIVE_API = "https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}"
THREADS_OEMBED_API = "https://www.threads.com/oembed/?url={url}&format=json"
TIKTOK_OEMBED_API = "https://www.tiktok.com/oembed?url={url}"
TWITCH_HELIX_CLIPS_API = "https://api.twitch.tv/helix/clips?id={clip_id}"
TWITCH_HELIX_USERS_API = "https://api.twitch.tv/helix/users?id={user_id}"
TWITCH_HELIX_USERS_LOGIN_API = "https://api.twitch.tv/helix/users?login={login}"
TWITCH_HELIX_STREAMS_API = "https://api.twitch.tv/helix/streams?user_login={login}"
TWITCH_HELIX_GAMES_API = "https://api.twitch.tv/helix/games?id={game_id}"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# Instagram internal web API. Unauthenticated requests 429 quickly;
# set INSTAGRAM_SESSION_ID in .env to inject a sessionid cookie.
INSTAGRAM_PROFILE_API = (
    "https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
)
INSTAGRAM_APP_ID = "936619743392459"

# Self-hosted InstaFix (github.com/Wikidepia/InstaFix).
# Docker: "instafix:3000" | Local dev: "localhost:3000"
# Configured via INSTAFIX_HOST env var → get_settings().instafix_host
INSTAGRAM_PROXY_URL = "http://{host}/{path}/{shortcode}/"
INSTAGRAM_ICON_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png"

# Scrapling sidecar host configured via SCRAPLING_HOST env var → get_settings().scrapling_host
THREADS_ICON_URL = "https://www.google.com/s2/favicons?domain=threads.com&sz=64"

# ── Colours ───────────────────────────────────────────────────────────────────

COLOR_INSTAGRAM = 0xE1306C
COLOR_THREADS = 0x101010
COLOR_BILIBILI = 0x00A1D6
COLOR_TIKTOK = 0x010101
COLOR_TWITCH = 0x9146FF

# ── Misc ──────────────────────────────────────────────────────────────────────

HTTP_TIMEOUT = 10.0
DESCRIPTION_LIMIT = 4096  # Discord embed description hard limit — do not lower
DISMISS_TIMEOUT = 120.0
VIDEO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB — Discord Level 1 Boost upload limit
