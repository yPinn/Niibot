"""scrapling sidecar — JS-rendered social media caption extraction.

Endpoints
---------
GET /threads?url=<threads-post-url>
  → 200 {"caption": "..."}   (empty string if not found)
  → 422 {"detail": "..."}    (invalid / missing url param)
  → 503 {"detail": "..."}    (browser not yet ready)
  → 500 {"detail": "..."}    (browser / navigation error)

GET /health → 200 {"status": "ok"}
"""

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from scrapling.fetchers import AsyncDynamicSession

LOGGER = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "3001"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_THREADS_SESSION_ID = unquote(os.getenv("THREADS_SESSION_ID", ""))

_THREADS_POST_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/(?:@[\w.]+/)?post/[\w-]+",
    re.IGNORECASE,
)

# Selectors tried in order; semantic selectors are preferred over atomic CSS classes.
# Atomic class selectors (x1a6qonq) may break on Meta redeploys — update as needed.
_CAPTION_SELECTORS = [
    "article [data-pressable-container] span[dir]::text",
    "article div[data-ad-rendering-role] span[dir]::text",
    "div[class*='x1a6qonq'] span[dir]::text",
]

# Navigation + hydration budget (ms). Sum must be well below bot-side HTTP timeout (35 s).
_GOTO_TIMEOUT_MS = 20_000
_ARTICLE_TIMEOUT_MS = 10_000

_session: AsyncDynamicSession | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _session
    LOGGER.info("scrapling: launching browser session …")
    async with AsyncDynamicSession(
        headless=True,
        disable_resources=True,
        block_ads=True,
        locale="en-US",
    ) as session:
        _session = session
        LOGGER.info("scrapling: browser ready")
        yield
    _session = None
    LOGGER.info("scrapling: browser closed")


app = FastAPI(title="scrapling", docs_url=None, redoc_url=None, lifespan=lifespan)


async def _scrape_threads_caption(post_url: str) -> str:
    """Navigate to a Threads post and extract the caption text via Scrapling."""
    if _session is None:
        raise RuntimeError("browser session is not initialised")

    t0 = time.monotonic()
    LOGGER.info("scrapling: scraping %s", post_url)

    async def _inject_cookie(page):  # type: ignore[no-untyped-def]
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

    try:
        response = await _session.fetch(
            post_url,
            wait_selector="article",
            timeout=_GOTO_TIMEOUT_MS + _ARTICLE_TIMEOUT_MS,
            load_dom=True,
            page_setup=_inject_cookie,
        )
        LOGGER.debug("scrapling: page ready (%.1f s)", time.monotonic() - t0)
    except Exception as exc:
        LOGGER.warning(
            "scrapling: navigation failed for %s (%.1f s): %s",
            post_url,
            time.monotonic() - t0,
            exc,
        )
        return ""

    for selector in _CAPTION_SELECTORS:
        try:
            texts = response.css(selector).getall()
            text = " ".join(t.strip() for t in texts if t.strip())
            if text:
                elapsed = time.monotonic() - t0
                LOGGER.info(
                    "scrapling: caption found (%d chars, %.1f s) via %r",
                    len(text),
                    elapsed,
                    selector,
                )
                return text
        except Exception as exc:
            LOGGER.debug("scrapling: selector %r failed: %s", selector, exc)

    elapsed = time.monotonic() - t0
    LOGGER.warning(
        "scrapling: no caption found for %s (%.1f s) "
        "— selectors may need updating or post requires login",
        post_url,
        elapsed,
    )
    return ""


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/threads")
async def get_threads_caption(
    url: str = Query(..., description="Threads post URL"),
) -> dict[str, str]:
    if not _THREADS_POST_RE.fullmatch(url):
        raise HTTPException(status_code=422, detail="url must be a valid Threads post URL")
    if _session is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    try:
        caption = await _scrape_threads_caption(url)
    except Exception as exc:
        LOGGER.error("scrapling: unhandled error for %s: %s", url, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"caption": caption}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        log_level=LOG_LEVEL.lower(),
    )
