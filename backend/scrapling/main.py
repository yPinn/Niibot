"""scrapling sidecar — Threads post data extraction via authenticated browser.

Launches a persistent Playwright/Chromium session with stealth patches and a
logged-in Threads session cookie. On each request:
  1. Navigates to the post URL with the session cookie injected (page_setup).
  2. Waits for the post container to appear and for the network to go idle.
  3. Runs page_action to poll every 300 ms (up to 6 s) for real content, then
     extracts the caption and engagement counts from the rendered DOM.

Endpoints: GET /threads, GET /threads/profile, GET /health.
Contract and response shapes: docs/integrations/scrapling.md.
"""

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import unquote, urlparse

import uvicorn
from browser_admission import BrowserAdmission, BrowserBusyError
from fastapi import FastAPI, HTTPException, Query
from scrapling.fetchers import AsyncDynamicSession

PORT = int(os.getenv("PORT", "3001"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "").lower() == "production"
_ERROR_WEBHOOK_URL = os.getenv("ERROR_WEBHOOK_URL", "") if _IS_PRODUCTION else ""

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class _HealthFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_HealthFilter())
if _ERROR_WEBHOOK_URL:
    from discord_webhook_handler import DiscordWebhookHandler

    logging.getLogger().addHandler(
        DiscordWebhookHandler(_ERROR_WEBHOOK_URL, service_name="scrapling")
    )

LOGGER: logging.Logger = logging.getLogger(__name__)
_THREADS_SESSION_ID = unquote(os.getenv("THREADS_SESSION_ID", ""))
_COOKIES_PATH = os.getenv("COOKIES_PATH", "/app/cookies.json")
_STEALTH_JS_PATH = os.path.join(os.path.dirname(__file__), "stealth.js")

_THREADS_POST_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/(?:@[\w.]+/)?post/[\w-]+",
    re.IGNORECASE,
)

_THREADS_PROFILE_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/@([\w.]+)/?$",
    re.IGNORECASE,
)

_FETCH_TIMEOUT_MS = 30_000
_CONTENT_POLL_INTERVAL_MS = 300

_LOGIN_URL_RE = re.compile(r"/login", re.IGNORECASE)
_CONTENT_WAIT_MAX_MS = 6_000

_session: AsyncDynamicSession | None = None
_browser_admission = BrowserAdmission(max_queue_depth=1, max_wait_seconds=25.0)

_ui_re = re.compile(r"^(Translate|See translation|See more|See less|\d+/\d+)$", re.I)
_thread_num_re = re.compile(r"^[\d/]+$")


def _clean_span(raw: str) -> str:
    raw = raw.replace("\u00a0", " ")
    lines = raw.splitlines()
    cut = next((i for i, line in enumerate(lines) if _ui_re.match(line.strip())), None)
    return "\n".join(lines[:cut] if cut is not None else lines).strip()


async def _inject_cookie(page) -> None:  # type: ignore[no-untyped-def]
    """Inject auth cookies: prefer persisted cookie file, fall back to env var."""
    if _COOKIES_PATH and os.path.exists(_COOKIES_PATH):
        try:
            with open(_COOKIES_PATH) as f:
                cookies = json.load(f)
            await page.context.add_cookies(cookies)
            LOGGER.debug("scrapling: loaded %d cookies from %s", len(cookies), _COOKIES_PATH)
            return
        except Exception as exc:
            LOGGER.warning(
                "scrapling: failed to load cookie file (%s), falling back to env var", exc
            )

    if _THREADS_SESSION_ID:
        await page.context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": _THREADS_SESSION_ID,
                    "domain": ".threads.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                }
            ]
        )


async def _persist_cookies(page) -> None:  # type: ignore[no-untyped-def]
    """Save the current browser context cookies to disk so session stays alive."""
    if not _COOKIES_PATH:
        return
    try:
        cookies = await page.context.cookies()
        with open(_COOKIES_PATH, "w") as f:
            json.dump(cookies, f)
        LOGGER.debug("scrapling: persisted %d cookies to %s", len(cookies), _COOKIES_PATH)
    except Exception as exc:
        LOGGER.debug("scrapling: failed to persist cookies: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _session
    LOGGER.info("scrapling: launching browser session …")
    if not _THREADS_SESSION_ID:
        LOGGER.warning("scrapling: THREADS_SESSION_ID not set — all requests unauthenticated")

    async with AsyncDynamicSession(
        headless=True,
        locale="en-US",
        init_script=_STEALTH_JS_PATH,
        extra_flags=["--disable-blink-features=AutomationControlled"],
        google_search=True,
    ) as session:
        _session = session
        LOGGER.info("scrapling: browser ready")
        yield
    _session = None
    LOGGER.info("scrapling: browser closed")


app = FastAPI(title="scrapling", docs_url=None, redoc_url=None, lifespan=lifespan)


async def _get_post_data(post_url: str) -> dict[str, Any]:
    if _session is None:
        raise RuntimeError("browser session is not initialised")

    t0 = time.monotonic()
    LOGGER.info("scrapling: fetching %s", post_url)

    result_holder: list[dict[str, Any]] = []

    # Extract the post ID for URL verification (guards against SPA stale DOM).
    # Use the post ID rather than the full path so Threads canonical redirects
    # (e.g. /@user/post/ID → /t/ID) don't break the check.
    _post_id = urlparse(post_url).path.rstrip("/").rsplit("/", 1)[-1]

    async def _extract_after_load(page):  # type: ignore[no-untyped-def]
        def _is_auth_wall(url: str) -> bool:
            parsed = urlparse(url)
            return bool(_LOGIN_URL_RE.search(url)) or parsed.path in ("", "/")

        if _is_auth_wall(page.url):
            LOGGER.warning(
                "scrapling: login redirect detected (%s) — THREADS_SESSION_ID may have expired",
                page.url,
            )
            result_holder.append({"_reason": "login_wall"})
            return

        deadline = time.monotonic() + _CONTENT_WAIT_MAX_MS / 1000

        while time.monotonic() < deadline:
            # Guard: Threads is a SPA — old page DOM may still be present right after
            # navigation. Skip extraction until the URL contains the target post ID.
            if _is_auth_wall(page.url) or _post_id not in urlparse(page.url).path:
                LOGGER.debug(
                    "scrapling: URL not yet updated (expected post_id=%s in %s), waiting…",
                    _post_id,
                    page.url,
                )
                await asyncio.sleep(_CONTENT_POLL_INTERVAL_MS / 1000)
                continue

            try:
                result = await page.evaluate("""
                    () => {
                        const first = document.querySelector('[data-pressable-container]');
                        if (!first) return null;

                        const captionTexts = [];
                        first.querySelectorAll('[class*="x1a6qonq"] span[dir]').forEach(el => {
                            const text = (el.innerText || el.textContent || '').trim();
                            if (text) captionTexts.push(text);
                        });

                        // Engagement counts: SVG <title> inside role=button identifies the action type.
                        const counts = {};
                        first.querySelectorAll('[role="button"]').forEach(btn => {
                            const svgTitle = btn.querySelector('svg title');
                            const key = svgTitle ? svgTitle.textContent.trim().toLowerCase() : '';
                            if (!['like','reply','repost','share'].includes(key)) return;
                            const text = (btn.innerText || '').trim().split('\\n')[0].trim();
                            if (text) counts[key + '_count'] = text;
                        });

                        const mediaItems = [];
                        const _seenPaths = new Set();
                        first.querySelectorAll('video, img[src]').forEach(el => {
                            if (el.tagName === 'VIDEO') {
                                const src = el.currentSrc || el.src
                                    || el.querySelector('source[src]')?.src || '';
                                if (!src.startsWith('http')) return;
                                const path = src.split('?')[0];
                                if (_seenPaths.has(path)) return;
                                _seenPaths.add(path);
                                mediaItems.push({type: 'video', url: src});
                            } else {
                                // Skip profile-picture links (/@handle with no /post/ segment).
                                // Post images are also wrapped in /@handle/post/… links, so
                                // the old `a[href*="/@"]` filter incorrectly dropped them.
                                const parentLink = el.closest('a[href*="/@"]');
                                if (parentLink && !parentLink.href.includes('/post/')) return;
                                const src = el.src;
                                if (!src.startsWith('http')) return;
                                const noqs = src.split('?')[0];
                                if (noqs.indexOf('.fbcdn.net') !== -1 && noqs.indexOf('-19/') !== -1) return;
                                if (_seenPaths.has(noqs)) return;
                                _seenPaths.add(noqs);
                                const _btn = el.closest('[role="button"]') || el.parentElement;
                                const _v = _btn ? _btn.querySelector('video') : null;
                                const _vs = _v ? (_v.currentSrc || _v.src || '') : '';
                                if (src.indexOf('/t51.71878-') !== -1) {
                                    if (!_vs.startsWith('http')) {
                                        mediaItems.push({type: 'placeholder', url: src});
                                    }
                                } else if (!_vs.startsWith('http')) {
                                    mediaItems.push({type: 'image', url: src});
                                }
                            }
                        });

                        return {captions: captionTexts, counts, mediaItems};
                    }
                """)
                LOGGER.debug(
                    "scrapling: page_action result=%s", str(result)[:120] if result else None
                )
                if result and (result.get("captions") or result.get("mediaItems")):
                    cleaned_spans = [
                        c
                        for t in result.get("captions", [])
                        if not _thread_num_re.fullmatch(t.strip()) and (c := _clean_span(t))
                    ]
                    caption = "\n".join(cleaned_spans).strip()
                    caption = re.sub(r"(\n\d+\n/\n\d+)+\s*$", "", caption).strip()
                    media_items: list[dict[str, str]] = result.get("mediaItems", [])

                    if not any(m["type"] == "video" for m in media_items):
                        try:
                            lazy_videos = await page.evaluate("""
                                async () => {
                                    const first = document.querySelector('[data-pressable-container]');
                                    if (!first) return [];

                                    const preloaded = [];
                                    document.querySelectorAll('link[rel="preload"][as="video"][href]')
                                        .forEach(l => { if (l.href.startsWith('http')) preloaded.push(l.href); });
                                    if (preloaded.length) return preloaded;

                                    const targets = new Set();
                                    Array.from(first.querySelectorAll('video'))
                                        .filter(v => !v.currentSrc && !v.src
                                            && !v.querySelector('source[src]'))
                                        .forEach(v => {
                                            const t = v.closest('[role="button"]') || v.parentElement;
                                            if (t) targets.add(t);
                                        });
                                    Array.from(first.querySelectorAll('img[src]'))
                                        .filter(img => !img.closest('a[href*="/@"]')
                                            && img.src.indexOf('/t51.71878-') !== -1)
                                        .forEach(img => {
                                            const t = img.closest('[role="button"]') || img.parentElement;
                                            if (t) targets.add(t);
                                        });
                                    if (!targets.size) return [];
                                    for (const t of targets) t.click();
                                    await new Promise(r => setTimeout(r, 1500));
                                    const urls = [];
                                    const _seenPaths = new Set();
                                    document.querySelectorAll('video').forEach(v => {
                                        const src = v.currentSrc || v.src
                                            || v.querySelector('source[src]')?.src || '';
                                        if (!src.startsWith('http')) return;
                                        const p = src.split('?')[0];
                                        if (_seenPaths.has(p)) return;
                                        _seenPaths.add(p);
                                        urls.push(src);
                                    });
                                    return urls;
                                }
                            """)
                            if lazy_videos:
                                LOGGER.debug("scrapling: lazy videos loaded: %d", len(lazy_videos))
                                vid_iter = iter(lazy_videos)
                                new_items: list[dict[str, str]] = []
                                for m in media_items:
                                    if m["type"] == "placeholder":
                                        url = next(vid_iter, None)
                                        if url:
                                            new_items.append({"type": "video", "url": url})
                                        else:
                                            # No video found — placeholder was a photo, keep as image.
                                            new_items.append({"type": "image", "url": m["url"]})
                                    else:
                                        new_items.append(m)
                                for url in vid_iter:
                                    new_items.append({"type": "video", "url": url})
                                media_items = new_items
                        except Exception as exc:
                            LOGGER.debug("scrapling: lazy video trigger failed: %s", exc)

                    image_urls = [m["url"] for m in media_items if m["type"] == "image"]
                    video_urls = [m["url"] for m in media_items if m["type"] == "video"]
                    result_holder.append(
                        {
                            "caption": caption,
                            **result["counts"],
                            "media_items": media_items,
                            "image_urls": image_urls,
                            "video_urls": video_urls,
                        }
                    )
                    await _persist_cookies(page)
                    return
            except Exception as exc:
                LOGGER.debug("scrapling: page_action eval error: %s", exc)
            await asyncio.sleep(_CONTENT_POLL_INTERVAL_MS / 1000)

        LOGGER.warning("scrapling: content wait timed out (%.1f s)", time.monotonic() - t0)

    try:
        await _session.fetch(
            post_url,
            timeout=_FETCH_TIMEOUT_MS,
            page_setup=_inject_cookie,
            page_action=_extract_after_load,
        )
    except Exception as exc:
        LOGGER.warning("scrapling: navigation failed (%.1f s): %s", time.monotonic() - t0, exc)
        return {"caption": "", "image_urls": [], "video_urls": []}

    if result_holder:
        data = result_holder[0]
        if data.get("_reason") == "login_wall":
            return {"caption": "", "image_urls": [], "video_urls": [], "_reason": "login_wall"}
        LOGGER.info(
            "scrapling: done — caption=%d chars counts=%s images=%d videos=%d (%.1f s)",
            len(data.get("caption", "")),
            {
                k: v
                for k, v in data.items()
                if k not in ("caption", "image_urls", "video_urls", "_reason")
            },
            len(data.get("image_urls", [])),
            len(data.get("video_urls", [])),
            time.monotonic() - t0,
        )
        return data

    LOGGER.warning("scrapling: no caption found (%.1f s)", time.monotonic() - t0)
    return {"caption": "", "image_urls": [], "video_urls": []}


async def _get_profile_data(profile_url: str) -> dict[str, Any]:
    if _session is None:
        raise RuntimeError("browser session is not initialised")

    t0 = time.monotonic()
    LOGGER.info("scrapling: fetching profile %s", profile_url)
    result_holder: list[dict[str, Any]] = []

    async def _extract_profile(page):  # type: ignore[no-untyped-def]
        def _is_auth_wall(url: str) -> bool:
            parsed = urlparse(url)
            return bool(_LOGIN_URL_RE.search(url)) or parsed.path in ("", "/")

        if _is_auth_wall(page.url):
            LOGGER.warning(
                "scrapling: login redirect detected (%s) — THREADS_SESSION_ID may have expired",
                page.url,
            )
            result_holder.append({"_reason": "login_wall"})
            return

        deadline = time.monotonic() + _CONTENT_WAIT_MAX_MS / 1000
        while time.monotonic() < deadline:
            try:
                result = await page.evaluate("""
                    () => {
                        const TABS = new Set(['Threads', 'Replies', 'Media', 'Reposts']);
                        const bioEl = Array.from(document.querySelectorAll('span[dir]'))
                            .filter(el => !el.closest('[data-pressable-container]'))
                            .find(el => {
                                const t = (el.innerText || el.textContent || '').trim();
                                if (t.length < 1 || t.length > 300) return false;
                                if (TABS.has(t)) return false;
                                if (/[\\d,.]+(K|M|B)?\\s+followers?/i.test(t)) return false;
                                if (/[\\d,.]+(K|M|B)?\\s+recent\\s+views?/i.test(t)) return false;
                                if (/^[\\w.]+$/.test(t)) return false; // pure ASCII username
                                return true;
                            });
                        const bio = bioEl ? (bioEl.innerText || bioEl.textContent || '').trim() : '';

                        let followers = '', recent_views = '';
                        document.querySelectorAll('span, a').forEach(el => {
                            if (el.closest('[data-pressable-container]')) return;
                            const txt = (el.innerText || el.textContent || '').trim();
                            const fmatch = txt.match(/^([\\d,.KMB]+)\\s+followers?$/i);
                            if (fmatch) { followers = fmatch[1]; return; }
                            const vmatch = txt.match(/^([\\d,.KMB]+)\\s+recent\\s+views?$/i);
                            if (vmatch) { recent_views = vmatch[1]; }
                        });

                        return bio || followers ? {bio, followers, recent_views} : null;
                    }
                """)
                LOGGER.debug("scrapling: profile result=%s", result)
                if result is not None:
                    result_holder.append(result)
                    await _persist_cookies(page)
                    return
            except Exception as exc:
                LOGGER.debug("scrapling: profile eval error: %s", exc)
            await asyncio.sleep(_CONTENT_POLL_INTERVAL_MS / 1000)
        LOGGER.warning("scrapling: profile wait timed out (%.1f s)", time.monotonic() - t0)

    try:
        await _session.fetch(
            profile_url,
            timeout=_FETCH_TIMEOUT_MS,
            page_setup=_inject_cookie,
            page_action=_extract_profile,
        )
    except Exception as exc:
        LOGGER.warning("scrapling: profile navigation failed: %s", exc)
        return {}

    if result_holder:
        data = result_holder[0]
        if data.get("_reason") == "login_wall":
            return {"_reason": "login_wall"}
        LOGGER.info(
            "scrapling: profile done — bio=%d chars followers=%r (%.1f s)",
            len(data.get("bio", "")),
            data.get("followers"),
            time.monotonic() - t0,
        )
        return data

    return {}


@app.get("/threads/profile")
async def get_threads_profile(
    url: str = Query(..., description="Threads profile URL"),
) -> dict[str, Any]:
    if not _THREADS_PROFILE_RE.fullmatch(url):
        raise HTTPException(status_code=422, detail="url must be a valid Threads profile URL")
    if _session is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    try:
        async with _browser_admission.acquire():
            return await _get_profile_data(url)
    except BrowserBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail="browser busy",
            headers={"Retry-After": "1"},
        ) from exc
    except Exception as exc:
        LOGGER.error("scrapling: unhandled profile error for %s: %s", url, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/threads")
async def get_threads_post(
    url: str = Query(..., description="Threads post URL"),
) -> dict[str, Any]:
    if not _THREADS_POST_RE.fullmatch(url):
        raise HTTPException(status_code=422, detail="url must be a valid Threads post URL")
    if _session is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    try:
        async with _browser_admission.acquire():
            return await _get_post_data(url)
    except BrowserBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail="browser busy",
            headers={"Retry-After": "1"},
        ) from exc
    except Exception as exc:
        LOGGER.error("scrapling: unhandled error for %s: %s", url, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        log_level=LOG_LEVEL.lower(),
    )
