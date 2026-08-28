"""Pure parsing helpers for the social-preview cog.

OpenGraph tag extraction and Twitch clip MP4-URL derivation — no I/O, no
Discord objects, so these stay trivially unit-testable on their own.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_TWITCH_THUMB_RE = re.compile(r"-preview-\d+x\d+\.jpg$", re.IGNORECASE)


def _twitch_clip_mp4_url(thumbnail_url: str) -> str | None:
    """Derive the direct MP4 URL from a Twitch clip thumbnail URL.

    Twitch CDN pattern: <base>-preview-<W>x<H>.jpg → <base>.mp4
    Returns None if the thumbnail URL doesn't match the expected pattern.
    """
    if not thumbnail_url or not _TWITCH_THUMB_RE.search(thumbnail_url):
        return None
    return _TWITCH_THUMB_RE.sub(".mp4", thumbnail_url)


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
