"""Unit tests for shared.instafix_client — Instagram Reel resolution via InstaFix.

Covers OG parsing/title extraction, share-link redirect resolution, and the
InstaFix redirect-follow calls (thumbnail, mp4 source, and the duration
embedded in the mp4 redirect's `efg` param) — all against a fake aiohttp
session, same style as test_bilibili_client.py.
"""

from __future__ import annotations

import base64
import json

import pytest

import shared.instafix_client as ic

_HOST = "instafix:3000"


def _mp4_url(*, duration_s: int | None = None, efg_override: str | None = None) -> str:
    """Build a CDN mp4 URL with an `efg` param shaped like Instagram's real one."""
    if efg_override is not None:
        efg = efg_override
    elif duration_s is not None:
        payload = json.dumps({"duration_s": duration_s}).encode()
        efg = base64.b64encode(payload).decode().rstrip("=")  # match real efg (no padding)
    else:
        return "https://cdn.example/video.mp4?sig=abc"
    return f"https://cdn.example/video.mp4?sig=abc&efg={efg}"


# ---------------------------------------------------------------------------
# fake aiohttp session
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, *, status=200, headers=None, text_body="", final_url=None):
        self.status = status
        self.headers = headers or {}
        self._text = text_body
        self.url = final_url or ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def text(self):
        return self._text


class _FakeSession:
    """Routes GET by URL substring. `routes` maps substring -> _FakeResp factory."""

    def __init__(self, routes):
        self._routes = routes
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kw):
        self.calls.append((str(url), kw))
        for needle, factory in self._routes.items():
            if needle in str(url):
                return factory()
        return _FakeResp(status=404)

    async def close(self):
        return None


class _RaisingSession:
    """A session whose .get() raises synchronously — simulates a network error."""

    def get(self, url, **kw):
        raise ConnectionError("boom")

    async def close(self):
        return None


# ---------------------------------------------------------------------------
# extract_instagram_shortcode / resolve_instagram_url
# ---------------------------------------------------------------------------


def test_extract_shortcode_from_reel_url():
    assert ic.extract_instagram_shortcode("https://www.instagram.com/reel/Cabc123/") == "Cabc123"


def test_extract_shortcode_from_reels_plural():
    assert ic.extract_instagram_shortcode("https://instagram.com/reels/Cabc123/") == "Cabc123"


def test_extract_shortcode_no_match():
    assert ic.extract_instagram_shortcode("https://example.com/not-instagram") is None


@pytest.mark.asyncio
class TestResolveInstagramUrl:
    async def test_direct_reel_url_no_http_call(self):
        shortcode = await ic.resolve_instagram_url("https://www.instagram.com/reel/Cabc123/")
        assert shortcode == "Cabc123"

    async def test_share_link_resolves_via_redirect(self):
        session = _FakeSession(
            {
                "share": lambda: _FakeResp(final_url="https://www.instagram.com/reel/Cabc123/"),
            }
        )
        shortcode = await ic.resolve_instagram_url(
            "https://www.instagram.com/share/abcXYZ", session=session
        )
        assert shortcode == "Cabc123"

    async def test_non_instagram_url_returns_none(self):
        assert await ic.resolve_instagram_url("https://example.com/whatever") is None

    async def test_share_link_failure_fails_open(self):
        shortcode = await ic.resolve_instagram_url(
            "https://www.instagram.com/share/abcXYZ", session=_RaisingSession()
        )
        assert shortcode is None


# ---------------------------------------------------------------------------
# _extract_is_vertical — pure
# ---------------------------------------------------------------------------


def test_is_vertical_true_when_taller_than_wide():
    og = {"video:width": "720", "video:height": "1280"}
    assert ic._extract_is_vertical(og) is True


def test_is_vertical_false_when_wider_than_tall():
    og = {"video:width": "1280", "video:height": "720"}
    assert ic._extract_is_vertical(og) is False


def test_is_vertical_defaults_true_when_dimensions_missing():
    assert ic._extract_is_vertical({}) is True


def test_is_vertical_defaults_true_when_dimensions_unparseable():
    og = {"video:width": "unknown", "video:height": "1280"}
    assert ic._extract_is_vertical(og) is True


def test_is_vertical_defaults_true_when_dimensions_zero():
    og = {"video:width": "0", "video:height": "0"}
    assert ic._extract_is_vertical(og) is True


# ---------------------------------------------------------------------------
# _extract_display_title — pure
# ---------------------------------------------------------------------------


def test_display_title_prefers_caption_over_handle():
    og = {"description": "晒干了我不沉默", "title": "@wuzhunxiao1"}
    assert ic._extract_display_title(og) == "晒干了我不沉默"


def test_display_title_strips_trailing_hashtags():
    og = {"description": "晒干了我不沉默\n#晒干了沉默 #游泳 #吴准笑教游泳"}
    assert ic._extract_display_title(og) == "晒干了我不沉默"


def test_display_title_collapses_embedded_newlines():
    og = {"description": "line one\nline two\nline three"}
    assert ic._extract_display_title(og) == "line one line two line three"


def test_display_title_truncates_past_max_length():
    og = {"description": "x" * 200}
    title = ic._extract_display_title(og)
    assert title is not None
    assert len(title) == ic._TITLE_MAX_LENGTH
    assert title.endswith("…")


def test_display_title_no_truncation_when_under_limit():
    og = {"description": "short caption"}
    assert ic._extract_display_title(og) == "short caption"


def test_display_title_falls_back_to_handle_when_caption_is_only_hashtags():
    og = {"description": "#a #b #c", "title": "@alice"}
    assert ic._extract_display_title(og) == "@alice"


def test_display_title_falls_back_to_handle_when_no_description():
    og = {"title": "Alice on Instagram: 'hi'"}
    assert ic._extract_display_title(og) == "Alice"


def test_display_title_none_when_neither_present():
    assert ic._extract_display_title({}) is None


# ---------------------------------------------------------------------------
# _extract_duration_seconds — pure, vectored
# ---------------------------------------------------------------------------

# Reference vector: a real `efg` value observed on a live InstaFix-resolved
# Instagram CDN URL (see docs/architecture/video-queue-platforms.md's
# Instagram Reel section) — decodes to {"duration_s": 16, ...}.
_REAL_EFG_URL = (
    "https://scontent.cdninstagram.com/o1/v/t2/f2/m86/example.mp4"
    "?_nc_cat=100&efg=eyJ2ZW5jb2RlX3RhZyI6Inhwdl9wcm9ncmVzc2l2ZS5JTlNUQUdSQU0uQ0xJUFMuQzMuNzIwLmRhc2hfYmFzZWxpbmVfMV92MSIs"
    "Inhwdl9hc3NldF9pZCI6NDUzNTEwMjA0MDEwODg4NCwiYXNzZXRfYWdlX2RheXMiOjI1LCJ2aV91c2VjYXNlX2lkIjoxMDA5OSwiZHVyYXRpb25fcyI6MTYs"
    "InVybGdlbl9zb3VyY2UiOiJ3d3cifQ%3D%3D&oe=6AADCA71"
)


def test_extract_duration_matches_real_instagram_reference_vector():
    assert ic._extract_duration_seconds(_REAL_EFG_URL) == 16


def test_extract_duration_no_efg_param():
    assert ic._extract_duration_seconds("https://cdn.example/video.mp4?sig=abc") is None


def test_extract_duration_malformed_base64():
    assert ic._extract_duration_seconds(_mp4_url(efg_override="!!!not-base64!!!")) is None


def test_extract_duration_valid_base64_non_json():
    bad = base64.b64encode(b"not json at all").decode().rstrip("=")
    assert ic._extract_duration_seconds(_mp4_url(efg_override=bad)) is None


def test_extract_duration_json_without_duration_field():
    payload = base64.b64encode(json.dumps({"other": "field"}).encode()).decode().rstrip("=")
    assert ic._extract_duration_seconds(_mp4_url(efg_override=payload)) is None


# ---------------------------------------------------------------------------
# fetch_instagram_reel_info
# ---------------------------------------------------------------------------


def _og_html(title: str, image_path: str) -> str:
    return (
        "<html><head>"
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:image" content="{image_path}">'
        "</head></html>"
    )


@pytest.mark.asyncio
class TestFetchInstagramReelInfo:
    async def test_title_thumbnail_and_duration_resolved(self):
        session = _FakeSession(
            {
                "/reel/Cabc123/": lambda: _FakeResp(
                    text_body=_og_html("Alice on Instagram: 'caption'", "/images/xyz")
                ),
                "/images/xyz": lambda: _FakeResp(
                    status=302, headers={"Location": "https://cdn.example/thumb.jpg"}
                ),
                "/videos/Cabc123/1": lambda: _FakeResp(
                    status=302, headers={"Location": _mp4_url(duration_s=16)}
                ),
            }
        )
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.title == "Alice"
        assert info.thumbnail_url == "https://cdn.example/thumb.jpg"
        assert info.duration_seconds == 16
        # No video:width/height in _og_html — defaults to True.
        assert info.is_vertical is True

    async def test_landscape_reel_detected_from_video_dimensions(self):
        html = (
            "<html><head>"
            '<meta property="og:title" content="@alice">'
            '<meta property="og:video:width" content="1280">'
            '<meta property="og:video:height" content="720">'
            "</head></html>"
        )
        session = _FakeSession({"/reel/Cabc123/": lambda: _FakeResp(text_body=html)})
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.is_vertical is False

    async def test_twitter_title_preferred_when_no_og_suffix(self):
        html = '<html><head><meta name="twitter:title" content="@alice"></head></html>'
        session = _FakeSession({"/reel/Cabc123/": lambda: _FakeResp(text_body=html)})
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.title == "@alice"
        assert info.thumbnail_url is None
        assert info.duration_seconds is None

    async def test_instafix_redirect_back_to_instagram_fails_open(self):
        session = _FakeSession(
            {
                "/reel/Cabc123/": lambda: _FakeResp(
                    status=302, headers={"Location": "https://www.instagram.com/reel/Cabc123/"}
                ),
            }
        )
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.title is None
        assert info.thumbnail_url is None
        assert info.duration_seconds is None

    async def test_non_200_fails_open(self):
        session = _FakeSession({"/reel/Cabc123/": lambda: _FakeResp(status=500)})
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.title is None
        assert info.thumbnail_url is None
        assert info.duration_seconds is None

    async def test_fetch_error_fails_open(self):
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=_RaisingSession())
        assert info.title is None
        assert info.thumbnail_url is None
        assert info.duration_seconds is None

    async def test_duration_missing_when_video_redirect_fails(self):
        # Title/thumbnail still resolve even if the video redirect (duration's
        # source) fails independently — they're concurrent, unrelated requests.
        session = _FakeSession(
            {
                "/reel/Cabc123/": lambda: _FakeResp(
                    text_body=_og_html("Alice on Instagram: 'caption'", "/images/xyz")
                ),
                "/images/xyz": lambda: _FakeResp(
                    status=302, headers={"Location": "https://cdn.example/thumb.jpg"}
                ),
                "/videos/Cabc123/1": lambda: _FakeResp(status=404),
            }
        )
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.title == "Alice"
        assert info.thumbnail_url == "https://cdn.example/thumb.jpg"
        assert info.duration_seconds is None

    async def test_duration_missing_when_efg_malformed(self):
        session = _FakeSession(
            {
                "/reel/Cabc123/": lambda: _FakeResp(text_body=_og_html("@alice", "")),
                "/videos/Cabc123/1": lambda: _FakeResp(
                    status=302,
                    headers={"Location": _mp4_url(efg_override="not-valid-base64!!!")},
                ),
            }
        )
        info = await ic.fetch_instagram_reel_info("Cabc123", _HOST, session=session)
        assert info.duration_seconds is None


# ---------------------------------------------------------------------------
# fetch_instagram_reel_source — play-time mp4 resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchInstagramReelSource:
    async def test_resolves_mp4_url(self):
        session = _FakeSession(
            {
                "/videos/Cabc123/1": lambda: _FakeResp(
                    status=302, headers={"Location": "https://cdn.example/video.mp4?sig=abc"}
                ),
            }
        )
        url = await ic.fetch_instagram_reel_source("Cabc123", _HOST, session=session)
        assert url == "https://cdn.example/video.mp4?sig=abc"

    async def test_non_mp4_redirect_discarded(self):
        session = _FakeSession(
            {
                "/videos/Cabc123/1": lambda: _FakeResp(
                    status=302, headers={"Location": "https://cdn.example/thumb.jpg"}
                ),
            }
        )
        url = await ic.fetch_instagram_reel_source("Cabc123", _HOST, session=session)
        assert url is None

    async def test_no_redirect_returns_none(self):
        session = _FakeSession({"/videos/Cabc123/1": lambda: _FakeResp(status=404)})
        url = await ic.fetch_instagram_reel_source("Cabc123", _HOST, session=session)
        assert url is None

    async def test_fetch_error_fails_open(self):
        url = await ic.fetch_instagram_reel_source("Cabc123", _HOST, session=_RaisingSession())
        assert url is None
