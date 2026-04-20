"""scrapling sidecar — Threads post data extraction via authenticated browser.

Launches a persistent Playwright/Chromium session with stealth patches and a
logged-in Threads session cookie. On each request:
  1. Navigates to the post URL with the session cookie injected (page_setup).
  2. Waits for the post container to appear and for the network to go idle.
  3. Runs page_action to poll every 300 ms (up to 6 s) for real content, then
     extracts the caption and engagement counts from the rendered DOM.

Endpoints
---------
GET /threads?url=<threads-post-url>
  → 200 {"caption": "...", "like_count": "...", "reply_count": "...",
         "repost_count": "...", "share_count": "..."}
  → 422 {"detail": "..."}    (invalid / missing url param)
  → 503 {"detail": "..."}    (browser not yet ready)
  → 500 {"detail": "..."}    (unhandled error)

GET /health → 200 {"status": "ok"}
"""

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from scrapling.fetchers import AsyncDynamicSession

PORT = int(os.getenv("PORT", "3001"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger(__name__)
_THREADS_SESSION_ID = unquote(os.getenv("THREADS_SESSION_ID", ""))

_THREADS_POST_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/(?:@[\w.]+/)?post/[\w-]+",
    re.IGNORECASE,
)

_FETCH_TIMEOUT_MS = 30_000
_CONTENT_POLL_INTERVAL_MS = 300
_CONTENT_WAIT_MAX_MS = 6_000

_session: AsyncDynamicSession | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _session
    LOGGER.info("scrapling: launching browser session …")
    _stealth_js = os.path.join(os.path.dirname(__file__), "stealth.js")
    if not _THREADS_SESSION_ID:
        LOGGER.warning("scrapling: THREADS_SESSION_ID not set — all requests unauthenticated")

    async with AsyncDynamicSession(
        headless=True,
        locale="en-US",
        init_script=_stealth_js,
        extra_flags=["--disable-blink-features=AutomationControlled"],
        google_search=True,
    ) as session:
        _session = session
        LOGGER.info("scrapling: browser ready")
        yield
    _session = None
    LOGGER.info("scrapling: browser closed")


app = FastAPI(title="scrapling", docs_url=None, redoc_url=None, lifespan=lifespan)


async def _get_post_data(post_url: str) -> dict[str, str]:
    if _session is None:
        raise RuntimeError("browser session is not initialised")

    t0 = time.monotonic()
    LOGGER.info("scrapling: fetching %s", post_url)

    result_holder: list[dict[str, str]] = []

    async def _inject_cookie(page):  # type: ignore[no-untyped-def]
        if _THREADS_SESSION_ID:
            await page.context.add_cookies([{
                "name": "sessionid",
                "value": _THREADS_SESSION_ID,
                "domain": ".threads.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }])

    async def _extract_after_load(page):  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + _CONTENT_WAIT_MAX_MS / 1000

        while time.monotonic() < deadline:
            try:
                result = await page.evaluate("""
                    () => {
                        const first = document.querySelector('[data-pressable-container]');
                        if (!first) return null;

                        // x1a6qonq is Meta's atomic CSS class for the post body content area.
                        const captionTexts = [];
                        first.querySelectorAll('[class*="x1a6qonq"] span[dir]').forEach(el => {
                            const line = (el.innerText || el.textContent || '')
                                .split('\\n')[0].replace(/\\u00a0/g, ' ').trim();
                            if (line) captionTexts.push(line);
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

                        return {captions: captionTexts, counts};
                    }
                """)
                LOGGER.debug("scrapling: page_action result=%s", str(result)[:120] if result else None)
                if result and any(t.strip() for t in result["captions"]):
                    caption = " ".join(t for t in result["captions"] if t.strip()).strip()
                    result_holder.append({"caption": caption, **result["counts"]})
                    return
            except Exception as exc:
                LOGGER.debug("scrapling: page_action eval error: %s", exc)
            await asyncio.sleep(_CONTENT_POLL_INTERVAL_MS / 1000)

        LOGGER.warning("scrapling: content wait timed out (%.1f s)", time.monotonic() - t0)

    try:
        await _session.fetch(
            post_url,
            wait_selector="[data-pressable-container]",
            timeout=_FETCH_TIMEOUT_MS,
            page_setup=_inject_cookie,
            page_action=_extract_after_load,
        )
    except Exception as exc:
        LOGGER.warning("scrapling: navigation failed (%.1f s): %s", time.monotonic() - t0, exc)
        return {"caption": ""}

    if result_holder:
        data = result_holder[0]
        LOGGER.info(
            "scrapling: done — caption=%d chars counts=%s (%.1f s)",
            len(data.get("caption", "")),
            {k: v for k, v in data.items() if k != "caption"},
            time.monotonic() - t0,
        )
        return data

    LOGGER.warning("scrapling: no caption found (%.1f s)", time.monotonic() - t0)
    return {"caption": ""}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/threads")
async def get_threads_post(
    url: str = Query(..., description="Threads post URL"),
) -> dict[str, str]:
    if not _THREADS_POST_RE.fullmatch(url):
        raise HTTPException(status_code=422, detail="url must be a valid Threads post URL")
    if _session is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    try:
        return await _get_post_data(url)
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
