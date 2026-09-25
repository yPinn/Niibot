"""Unit tests for shared.bilibili_client — the risk-control-aware metadata client.

Covers the WBI/ticket crypto against Bilibili's published reference vectors and
the three-tier fallback (plain view API -> WBI view API -> webpage scrape),
including the fail-open behaviour every caller depends on.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from unittest.mock import patch

import pytest

import shared.bilibili_client as bc

# Reference vectors from bilibili-API-collect docs/misc/sign/wbi.md
_REF_IMG_KEY = "7cd084941338484aae1ad9425b84077c"
_REF_SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"
_REF_MIXIN_KEY = "ea1db124af3c7062474693fa704f4ff8"
_REF_WRID = "8f6f2b5b3d485fe1886cec6a0be8c5d4"  # for {foo:114,bar:514,zab:1919810,wts:1702204169}


@pytest.fixture(autouse=True)
def _clean_caches():
    bc._reset_caches_for_tests()
    yield
    bc._reset_caches_for_tests()


# ---------------------------------------------------------------------------
# crypto / signing — pure, vectored
# ---------------------------------------------------------------------------


def test_mixin_key_matches_reference_vector():
    assert bc._mixin_key(_REF_IMG_KEY, _REF_SUB_KEY) == _REF_MIXIN_KEY


def test_sign_wbi_matches_reference_vector():
    with patch("shared.bilibili_client.time.time", return_value=1702204169):
        signed = bc.sign_wbi({"foo": "114", "bar": "514", "zab": 1919810}, _REF_MIXIN_KEY)
    assert signed["wts"] == "1702204169"
    assert signed["w_rid"] == _REF_WRID


def test_sign_wbi_strips_special_chars_from_values():
    with patch("shared.bilibili_client.time.time", return_value=1_700_000_000):
        signed = bc.sign_wbi({"q": "a!b'c(d)e*f"}, _REF_MIXIN_KEY)
    assert signed["q"] == "abcdef"


def test_bili_ticket_hexsign_is_hmac_sha256():
    ts = 1_700_000_123
    expected = hmac.new(b"XgwSnGZ1p", f"ts{ts}".encode(), hashlib.sha256).hexdigest()
    assert bc._bili_ticket_hexsign(ts) == expected


def test_key_from_url_takes_basename_without_ext():
    assert bc._key_from_url("https://i0.hdslb.com/bfs/wbi/abc123.png") == "abc123"
    assert bc._key_from_url(None) == ""


@pytest.mark.asyncio
async def test_concurrent_wbi_key_misses_share_one_nav_request():
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingNav(_FakeResp):
        async def json(self, content_type=None):
            started.set()
            await release.wait()
            return await super().json(content_type)

    bc._bili_ticket = "cached-ticket"
    bc._bili_ticket_exp = time.time() + 10_000
    session = _FakeSession(
        {
            "/x/web-interface/nav": lambda: _BlockingNav(
                json_body={
                    "data": {
                        "wbi_img": {
                            "img_url": f"https://i0.hdslb.com/{_REF_IMG_KEY}.png",
                            "sub_url": f"https://i0.hdslb.com/{_REF_SUB_KEY}.png",
                        }
                    }
                }
            )
        }
    )

    first = asyncio.create_task(bc._ensure_mixin_key(session))
    await started.wait()
    second = asyncio.create_task(bc._ensure_mixin_key(session))
    await asyncio.sleep(0)
    assert session.count("/x/web-interface/nav") == 1

    release.set()
    assert await first == await second == _REF_MIXIN_KEY


# ---------------------------------------------------------------------------
# fake aiohttp session
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, *, status=200, json_body=None, text_body=""):
        self.status = status
        self._json = json_body
        self._text = text_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def json(self, content_type=None):
        if self._json is None:
            raise ValueError("no json body")
        return self._json

    async def text(self):
        return self._text


class _FakeSession:
    """Routes get/post by URL substring. `routes` maps substring -> _FakeResp factory."""

    def __init__(self, routes):
        self._routes = routes
        self.calls: list[tuple[str, str, dict]] = []

    def _resp(self, method, url, kw):
        self.calls.append((method, str(url), kw))
        for needle, factory in self._routes.items():
            if needle in str(url):
                return factory()
        return _FakeResp(status=404, json_body={"code": -404})

    def get(self, url, **kw):
        return self._resp("GET", url, kw)

    def post(self, url, **kw):
        return self._resp("POST", url, kw)

    async def close(self):
        return None

    def count(self, needle):
        return sum(1 for _, url, _ in self.calls if needle in url)


def _view_ok(bvid="BV1x", title="T", duration=90, view=1234, w=1920, h=1080):
    return _FakeResp(
        json_body={
            "code": 0,
            "data": {
                "bvid": bvid,
                "title": title,
                "duration": duration,
                "stat": {"view": view},
                "dimension": {"width": w, "height": h},
            },
        }
    )


def _blocked_412():
    return _FakeResp(status=412, text_body="")


def _v_voucher():
    return _FakeResp(json_body={"code": 0, "data": {"v_voucher": "voucher_abc"}})


def _nav_keys():
    return _FakeResp(
        json_body={
            "code": -101,
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{_REF_IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{_REF_SUB_KEY}.png",
                }
            },
        }
    )


def _ticket():
    return _FakeResp(
        json_body={
            "code": 0,
            "data": {"ticket": "tkt.jwt.sig", "created_at": int(time.time()), "ttl": 259200},
        }
    )


_WEBPAGE_HTML = (
    "<html><head></head><body><script>"
    'window.__INITIAL_STATE__={"videoData":{"bvid":"BV1web","title":"Web Title",'
    '"duration":321,"stat":{"view":9999},"dimension":{"width":1080,"height":1920}}};'
    "(function(){})();</script></body></html>"
)


@pytest.mark.asyncio
class TestFetchBilibiliVideoData:
    async def _run(self, routes):
        session = _FakeSession(routes)
        with patch("aiohttp.ClientSession", return_value=session):
            data = await bc.fetch_bilibili_video_data("BV1x")
        return data, session

    async def test_tier_b_plain_view_success(self):
        data, session = await self._run(
            {"/x/web-interface/view": _view_ok, "GenWebTicket": _ticket}
        )
        assert data["title"] == "T"
        assert data["duration"] == 90
        assert session.count("wbi/view") == 0
        assert session.count("www.bilibili.com/video/") == 0

    async def test_412_falls_through_to_wbi_view(self):
        data, session = await self._run(
            {
                "/x/web-interface/wbi/view": _view_ok,
                "/x/web-interface/view": _blocked_412,
                "/x/web-interface/nav": _nav_keys,
                "GenWebTicket": _ticket,
            }
        )
        assert data["duration"] == 90
        # the wbi/view call carried a signature
        wbi_call = next(kw for _, url, kw in session.calls if "wbi/view" in url)
        assert "w_rid" in wbi_call["params"] and "wts" in wbi_call["params"]

    async def test_v_voucher_falls_through_to_webpage(self):
        data, session = await self._run(
            {
                "/x/web-interface/wbi/view": _v_voucher,
                "/x/web-interface/view": _v_voucher,
                "/x/web-interface/nav": _nav_keys,
                "GenWebTicket": _ticket,
                "www.bilibili.com/video/": lambda: _FakeResp(text_body=_WEBPAGE_HTML),
            }
        )
        assert data["bvid"] == "BV1web"
        assert data["duration"] == 321
        assert data["dimension"] == {"width": 1080, "height": 1920}

    async def test_all_tiers_blocked_returns_none(self):
        data, _ = await self._run(
            {
                "/x/web-interface/wbi/view": _blocked_412,
                "/x/web-interface/view": _blocked_412,
                "/x/web-interface/nav": _nav_keys,
                "GenWebTicket": _ticket,
                "www.bilibili.com/video/": _blocked_412,
            }
        )
        assert data is None

    async def test_terminal_code_stops_before_other_tiers(self):
        def _gone():
            return _FakeResp(json_body={"code": -404, "message": "啥都木有", "data": None})

        session = _FakeSession({"/x/web-interface/view": _gone, "GenWebTicket": _ticket})
        with patch("aiohttp.ClientSession", return_value=session):
            data = await bc.fetch_bilibili_video_data("BV1x")
        assert data is None
        assert session.count("wbi/view") == 0
        assert session.count("www.bilibili.com/video/") == 0

    async def test_terminal_code_uses_short_negative_cache(self):
        def _gone():
            return _FakeResp(json_body={"code": -404, "message": "gone", "data": None})

        session = _FakeSession({"/x/web-interface/view": _gone, "GenWebTicket": _ticket})
        with patch("aiohttp.ClientSession", return_value=session):
            first = await bc.fetch_bilibili_video_data("BVnegative1")
            second = await bc.fetch_bilibili_video_data("BVnegative1")

        assert first is second is None
        assert session.count("/x/web-interface/view") == 1

    async def test_success_is_cached_by_bvid(self):
        session = _FakeSession({"/x/web-interface/view": _view_ok, "GenWebTicket": _ticket})
        with patch("aiohttp.ClientSession", return_value=session):
            first = await bc.fetch_bilibili_video_data("BVcached001")
            second = await bc.fetch_bilibili_video_data("BVcached001")

        assert first == second
        assert session.count("/x/web-interface/view") == 1

    async def test_risk_control_miss_is_not_cached(self):
        session = _FakeSession(
            {
                "/x/web-interface/wbi/view": _blocked_412,
                "/x/web-interface/view": _blocked_412,
                "/x/web-interface/nav": _nav_keys,
                "GenWebTicket": _ticket,
                "www.bilibili.com/video/": _blocked_412,
            }
        )
        with patch("aiohttp.ClientSession", return_value=session):
            await bc.fetch_bilibili_video_data("BVblocked01")
            await bc.fetch_bilibili_video_data("BVblocked01")

        assert session.count("/x/web-interface/view") == 2

    async def test_credentials_are_cached_across_calls(self):
        session = _FakeSession(
            {
                "/x/web-interface/view": _view_ok,
                "/x/web-interface/nav": _nav_keys,
                "GenWebTicket": _ticket,
            }
        )
        with patch("aiohttp.ClientSession", return_value=session):
            await bc.fetch_bilibili_video_data("BV1a")
            await bc.fetch_bilibili_video_data("BV1b")
        assert session.count("GenWebTicket") == 1  # ticket fetched once, then cached

    async def test_webpage_without_initial_state_returns_none(self):
        session = _FakeSession(
            {
                "/x/web-interface/wbi/view": _blocked_412,
                "/x/web-interface/view": _blocked_412,
                "/x/web-interface/nav": _nav_keys,
                "GenWebTicket": _ticket,
                "www.bilibili.com/video/": lambda: _FakeResp(text_body="<html>no state</html>"),
            }
        )
        with patch("aiohttp.ClientSession", return_value=session):
            data = await bc.fetch_bilibili_video_data("BV1x")
        assert data is None
