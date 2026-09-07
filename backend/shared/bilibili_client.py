"""Bilibili web metadata client — gets a video's `data` object past risk control.

UNOFFICIAL. Bilibili has no public Open-Platform API for reading an arbitrary
public video's metadata; every option here is a reverse-engineered web endpoint
with no SLA and no rate-limit contract (same class of dependency as the Twitch
private GraphQL call in ``video_sources.py``). The single documented behaviour
we rely on: a request that risk control does not like comes back as HTTP 412,
or as ``{"code": 0, "data": {"v_voucher": ...}}``, or ``code`` ``-412`` / ``-352``.

From a datacenter / container egress IP the bare ``x/web-interface/view`` call
Niibot used for a year now returns 412. The fix, cribbed from yt-dlp's
``bilibili.py`` and the community ``bilibili-API-collect`` docs, is three tiers,
each a fallback for the one before:

1. ``x/web-interface/view`` (non-WBI) with a browser ``User-Agent``, a
   ``.bilibili.com`` ``Referer``, a self-generated ``buvid3`` cookie and a
   cached ``bili_ticket`` (a 3-day HMAC-signed JWT that "lowers risk-control
   probability").
2. ``x/web-interface/wbi/view`` — same request plus a WBI ``w_rid`` / ``wts``
   signature. The mixin-key table is a constant Bilibili has not changed since
   WBI shipped in 2023; the per-day ``img_key`` / ``sub_key`` are fetched from
   ``x/web-interface/nav`` and cached.
3. Scrape ``https://www.bilibili.com/video/<bvid>`` and read
   ``window.__INITIAL_STATE__.videoData`` — the JSON the page hydrates from,
   the same shape as the API ``data`` object. This is yt-dlp's primary path.

Every tier fails open: on exhaustion the client returns ``None`` and callers
fall back to the ``metadata_best_effort`` handling in ``video_sources.py`` /
skip the Discord embed. Credentials (``buvid3``, ``bili_ticket``, the mixin
key) are cached at module scope as plain strings, so they survive the
throwaway sessions that callers without a shared ``aiohttp`` session create.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import aiohttp

LOGGER: logging.Logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = aiohttp.ClientTimeout(total=6)

_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
_WBI_VIEW_URL = "https://api.bilibili.com/x/web-interface/wbi/view"
_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
_TICKET_URL = "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket"
_WEBPAGE_URL = "https://www.bilibili.com/video/{bvid}"

# getMixinKey() reorder table — constant since WBI shipped (2023-03).
# Source: bilibili-API-collect docs/misc/sign/wbi.md, yt-dlp bilibili.py.
_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
)  # fmt: skip

_TICKET_HMAC_KEY = b"XgwSnGZ1p"  # bilibili-API-collect docs/misc/sign/bili_ticket.md
_TICKET_KEY_ID = "ec02"
_TICKET_REFRESH_MARGIN = 3600.0
_WBI_KEY_TTL = 3600.0

# `code` values where no tier can ever succeed — stop rather than burn requests.
_TERMINAL_CODES = frozenset({-400, -403, -404, 62002, 62004, 62012})

_INITIAL_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*")

_cred_lock = asyncio.Lock()
_buvid3: str | None = None
_b_nut: str | None = None
_bili_ticket: str = ""
_bili_ticket_exp: float = 0.0
_wbi_mixin_key: str = ""
_wbi_mixin_key_ts: float = 0.0


def _reset_caches_for_tests() -> None:
    """Drop every module-level credential cache. Test-only."""
    global _buvid3, _b_nut, _bili_ticket, _bili_ticket_exp, _wbi_mixin_key, _wbi_mixin_key_ts
    _buvid3 = _b_nut = None
    _bili_ticket = _wbi_mixin_key = ""
    _bili_ticket_exp = _wbi_mixin_key_ts = 0.0


def _bili_ticket_hexsign(ts: int) -> str:
    return hmac.new(_TICKET_HMAC_KEY, f"ts{ts}".encode(), hashlib.sha256).hexdigest()


def _mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB if i < len(raw))[:32]


def sign_wbi(params: dict[str, Any], mixin_key: str) -> dict[str, str]:
    """Add ``wts`` + ``w_rid`` to a query dict per the WBI algorithm."""
    signed: dict[str, str] = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in sorted({**params, "wts": int(time.time())}.items())
    }
    query = urlencode(signed)
    signed["w_rid"] = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    return signed


async def _ensure_ticket(session: aiohttp.ClientSession) -> str:
    """Fetch + cache a ``bili_ticket``; also primes the WBI mixin key. Best effort."""
    global _bili_ticket, _bili_ticket_exp, _wbi_mixin_key, _wbi_mixin_key_ts
    if _bili_ticket and time.time() < _bili_ticket_exp - _TICKET_REFRESH_MARGIN:
        return _bili_ticket
    ts = int(time.time())
    params = {
        "key_id": _TICKET_KEY_ID,
        "hexsign": _bili_ticket_hexsign(ts),
        "context[ts]": str(ts),
        "csrf": "",
    }
    try:
        async with session.post(
            f"{_TICKET_URL}?{urlencode(params)}",
            headers={"User-Agent": _UA, "Referer": "https://www.bilibili.com/"},
            timeout=_TIMEOUT,
        ) as resp:
            body = await resp.json(content_type=None)
        data = body.get("data") or {}
        ticket = data.get("ticket")
        if not ticket:
            LOGGER.warning("[Bilibili] ticket response had no ticket: code=%s", body.get("code"))
            return _bili_ticket
        _bili_ticket = ticket
        _bili_ticket_exp = float(data.get("created_at", ts)) + float(data.get("ttl", 259200))
        nav = data.get("nav") or {}
        img, sub = _key_from_url(nav.get("img")), _key_from_url(nav.get("sub"))
        if img and sub:
            _wbi_mixin_key = _mixin_key(img, sub)
            _wbi_mixin_key_ts = time.time()
        return _bili_ticket
    except Exception as exc:
        LOGGER.warning("[Bilibili] ticket fetch failed: %s", type(exc).__name__)
        return _bili_ticket


def _key_from_url(url: str | None) -> str:
    """`https://i0.hdslb.com/bfs/wbi/<key>.png` -> `<key>`."""
    if not url:
        return ""
    return url.rsplit("/", 1)[-1].split(".", 1)[0]


async def _ensure_mixin_key(session: aiohttp.ClientSession) -> str:
    """Fetch + cache the WBI mixin key (daily rotation). Empty string on failure."""
    global _wbi_mixin_key, _wbi_mixin_key_ts
    if _wbi_mixin_key and time.time() < _wbi_mixin_key_ts + _WBI_KEY_TTL:
        return _wbi_mixin_key
    try:
        async with session.get(
            _NAV_URL, headers=await _web_headers(session, referer="https://www.bilibili.com/")
        ) as resp:
            body = await resp.json(content_type=None)
        wbi_img = (body.get("data") or {}).get("wbi_img") or {}
        img, sub = _key_from_url(wbi_img.get("img_url")), _key_from_url(wbi_img.get("sub_url"))
        if not (img and sub):
            LOGGER.warning("[Bilibili] nav response had no wbi_img keys")
            return _wbi_mixin_key
        _wbi_mixin_key = _mixin_key(img, sub)
        _wbi_mixin_key_ts = time.time()
        return _wbi_mixin_key
    except Exception as exc:
        LOGGER.warning("[Bilibili] nav/wbi key fetch failed: %s", type(exc).__name__)
        return _wbi_mixin_key


async def _cookie_value(session: aiohttp.ClientSession) -> str:
    global _buvid3, _b_nut
    if _buvid3 is None:
        # yt-dlp self-generates rather than calling finger/spi — a random uuid works.
        _buvid3 = f"{uuid.uuid4()}infoc".upper()
        _b_nut = str(int(time.time()))
    parts = [f"buvid3={_buvid3}", f"b_nut={_b_nut}"]
    ticket = await _ensure_ticket(session)
    if ticket:
        parts.append(f"bili_ticket={ticket}")
    return "; ".join(parts)


async def _web_headers(
    session: aiohttp.ClientSession | None = None, *, referer: str = "https://www.bilibili.com/"
) -> dict[str, str]:
    """Browser-like headers + the risk-control cookie. Shared by every Bilibili call."""
    headers = {
        "User-Agent": _UA,
        "Referer": referer,
        "Origin": "https://www.bilibili.com",
    }
    if session is not None:
        async with _cred_lock:
            headers["Cookie"] = await _cookie_value(session)
    return headers


async def bilibili_web_headers(session: aiohttp.ClientSession | None = None) -> dict[str, str]:
    """Public: headers for other Bilibili web endpoints (card / live / space)."""
    own = session is None
    s = session or aiohttp.ClientSession()
    try:
        return await _web_headers(s)
    finally:
        if own:
            await s.close()


def _usable_data(body: dict[str, Any]) -> dict[str, Any] | None:
    """A view/wbi-view body -> its `data` object, or None if blocked / terminal."""
    code = body.get("code")
    data = body.get("data")
    if code == 0 and isinstance(data, dict) and data.get("bvid") and "v_voucher" not in data:
        return data
    if code in _TERMINAL_CODES:
        return None  # genuinely unavailable — caller should not retry other tiers
    return None


async def _try_view(
    session: aiohttp.ClientSession,
    bvid: str,
    headers: dict[str, str],
    *,
    signed_query: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Returns (data, is_terminal). is_terminal=True means stop trying other tiers."""
    url = _WBI_VIEW_URL if signed_query is not None else _VIEW_URL
    query = signed_query if signed_query is not None else {"bvid": bvid}
    try:
        async with session.get(url, params=query, headers=headers, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                LOGGER.info(
                    "[Bilibili] %s -> HTTP %s for %s", url.rsplit("/", 1)[-1], resp.status, bvid
                )
                return None, False
            body = await resp.json(content_type=None)
    except Exception as exc:
        LOGGER.warning("[Bilibili] %s request failed for %s: %s", url, bvid, type(exc).__name__)
        return None, False
    if body.get("code") in _TERMINAL_CODES:
        LOGGER.info("[Bilibili] %s terminal code %s for %s", url, body.get("code"), bvid)
        return None, True
    data = _usable_data(body)
    if data is None:
        LOGGER.info(
            "[Bilibili] %s blocked (code=%s, v_voucher=%s) for %s",
            url.rsplit("/", 1)[-1],
            body.get("code"),
            bool((body.get("data") or {}).get("v_voucher")),
            bvid,
        )
    return data, False


async def _try_webpage(
    session: aiohttp.ClientSession, bvid: str, headers: dict[str, str]
) -> dict[str, Any] | None:
    """Scrape `window.__INITIAL_STATE__.videoData` from the video page."""
    try:
        async with session.get(
            _WEBPAGE_URL.format(bvid=bvid), headers=headers, timeout=_TIMEOUT
        ) as resp:
            if resp.status != 200:
                LOGGER.info("[Bilibili] webpage -> HTTP %s for %s", resp.status, bvid)
                return None
            html = await resp.text()
    except Exception as exc:
        LOGGER.warning("[Bilibili] webpage fetch failed for %s: %s", bvid, type(exc).__name__)
        return None

    m = _INITIAL_STATE_RE.search(html)
    if not m:
        LOGGER.info("[Bilibili] webpage had no __INITIAL_STATE__ for %s", bvid)
        return None
    try:
        state, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError:
        LOGGER.info("[Bilibili] webpage __INITIAL_STATE__ did not parse for %s", bvid)
        return None
    video_data = state.get("videoData") if isinstance(state, dict) else None
    if isinstance(video_data, dict) and video_data.get("bvid"):
        return video_data
    return None


async def fetch_bilibili_video_data(
    bvid: str, *, session: aiohttp.ClientSession | None = None
) -> dict[str, Any] | None:
    """Fetch a Bilibili video's raw ``data`` object (``x/web-interface/view`` shape).

    Tries the plain view API, then the WBI-signed view API, then a webpage
    scrape. Returns ``None`` if every tier is blocked or the video is genuinely
    unavailable — callers must treat that as "metadata unknown", not "reject".
    """
    own = session is None
    s = session or aiohttp.ClientSession()
    try:
        headers = await _web_headers(s, referer=_WEBPAGE_URL.format(bvid=bvid))

        data, terminal = await _try_view(s, bvid, headers)
        if data is not None:
            return data
        if terminal:
            return None

        mixin_key = await _ensure_mixin_key(s)
        if mixin_key:
            signed = sign_wbi({"bvid": bvid, "platform": "web"}, mixin_key)
            data, terminal = await _try_view(s, bvid, headers, signed_query=signed)
            if data is not None:
                return data
            if terminal:
                return None

        return await _try_webpage(s, bvid, headers)
    except Exception as exc:
        LOGGER.warning(
            "[Bilibili] fetch_bilibili_video_data failed for %s: %s", bvid, type(exc).__name__
        )
        return None
    finally:
        if own:
            await s.close()
