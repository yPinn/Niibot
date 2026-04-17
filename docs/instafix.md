# InstaFix — Self-Hosted Instagram OG Proxy

## What It Is

[Wikidepia/InstaFix](https://github.com/Wikidepia/InstaFix) is a self-hosted proxy that returns static HTML with
OpenGraph tags for Instagram posts — bypassing the login wall that blocks server-side scraping.

Instagram blocks anonymous OG scraping. InstaFix acts as an intermediary, fetching post data and re-serving it
as OG-tagged HTML. Discord (and bots like Niibot) can then scrape the proxy instead of Instagram directly.

---

## Docker Setup

```yaml
services:
  instafix:
    image: ghcr.io/wikidepia/instafix:main
    container_name: niibot-instafix
    restart: unless-stopped
    networks:
      - niibot-network # internal only — no host port needed
    # No healthcheck — the image is a Go binary on a minimal base (no wget/curl).
    # discord-bot depends on instafix with condition: service_started, not service_healthy.
```

- **No `ports:` mapping required** — other services access it via Docker DNS (`instafix:3000`)
- Expose to host only for local dev debugging

### Environment Variable

```python
INSTAFIX_HOST = os.getenv("INSTAFIX_HOST", "instafix:3000")
# Local dev: INSTAFIX_HOST=localhost:3000
# Docker:    default "instafix:3000" works via DNS
```

---

## URL Patterns

All requests are **HTTP** (internal network, no TLS needed).

| Post type         | Proxy URL                                      | Notes                                                        |
| ----------------- | ---------------------------------------------- | ------------------------------------------------------------ |
| Photo post        | `http://{host}/p/{shortcode}/`                 | Returns OG tags                                              |
| Carousel (grid)   | `http://{host}/p/{shortcode}/`                 | `og:image` → `/grid/...` path                                |
| Carousel (single) | `http://{host}/p/{shortcode}/?img_index={n}`   | `og:image` → `/images/...` path                              |
| Reel              | InstaFix redirects Chrome UA back to Instagram | Skip proxy; fetch `instagram.com/reel/{shortcode}/` directly |
| TV                | Same as Reel                                   | Skip proxy                                                   |

---

## User-Agent Behaviour (Critical)

InstaFix **redirects Chrome/browser User-Agents back to Instagram** — you get a redirect instead of HTML.

```python
# REQUIRED for InstaFix requests
headers = {"User-Agent": "Discordbot/2.0"}

# For Instagram direct (reel/tv path — bypasses InstaFix entirely)
# Use bot UA too; Instagram serves OG to crawlers
```

Do **not** use the default browser UA with InstaFix — you will get a 302 to `instagram.com`.

---

## OG Tag Structure

```html
<!-- Photo / single image -->
<meta property="og:image" content="/images/abc123..." />
<meta property="og:title" content="@username" />
<!-- or "Name on Instagram: ..." -->
<meta property="og:description" content="caption text" />
<meta name="twitter:title" content="@username" />
<!-- fallback if og:title absent -->

<!-- Carousel (grid overview) -->
<meta property="og:image" content="/grid/shortcode.jpg" />

<!-- Carousel (img_index=n) -->
<meta property="og:image" content="/images/abc123..." />
```

**Key quirk:** `og:image` values are **relative paths**, not full URLs.
You must resolve them via InstaFix's redirect endpoint:

```text
GET http://{host}{img_path}
User-Agent: Discordbot/2.0
follow_redirects: False        ← important: only want the Location header
```

InstaFix returns a `302` to the Instagram CDN URL. Extract `response.headers["location"]`.

---

## Carousel Detection & Probing

```text
og:image starts with /grid/  → multi-image post → probe img_index=1..N
og:image starts with /images/ → single image → resolve redirect once
anything else                → unexpected; skip
```

**Probing strategy** (balance speed vs. completeness):

```python
# Phase 1: probe indices 1–4 concurrently
results = await asyncio.gather(*[fetch(i) for i in range(1, 5)])

# Phase 2: only if index 4 succeeded (carousel has >4 images)
if results[-1] is not None:
    results += await asyncio.gather(*[fetch(i) for i in range(5, 11)])

# Collect all resolved CDN URLs (filter, don't break-on-None)
cdn_urls = [cdn for cdn, _ in results if cdn is not None]
```

Max Instagram carousel size is 10 images.

---

## Title/Author Extraction

OG title formats vary by InstaFix version and post type:

| Format       | Example                           | Extract                                |
| ------------ | --------------------------------- | -------------------------------------- |
| Classic      | `"Alice on Instagram: 'caption'"` | Split on `" on Instagram"`, take `[0]` |
| Handle-only  | `"@alice"` or `"alice"`           | Use as-is                              |
| Newer format | populated in `twitter:title`      | Use `twitter:title` as fallback        |

```python
def _extract_author(raw_title: str, suffix: str) -> str | None:
    if suffix in raw_title:
        return raw_title.split(suffix)[0]
    return raw_title or None
```

---

## Reel / TV Handling

InstaFix does **not** reliably proxy Reels — it redirects Chrome UAs back to Instagram.
Fetch `instagram.com/reel/{shortcode}/` directly with `User-Agent: Discordbot/2.0` and `follow_redirects=True`.
Instagram serves OG tags to known crawlers without login for Reels.

---

## Path Validation (Security)

Before constructing `http://{host}{img_path}`:

```python
if not img_path.startswith("/"):
    LOGGER.warning("Unexpected InstaFix image path: %r", img_path)
    return None
```

Prevents SSRF if InstaFix ever returns a malformed or protocol-relative path.

---

## Integration Pattern (Niibot Reference)

```text
on_message → INSTAGRAM_RE match → _handle_instagram
  ├─ path in (reel, tv) → fetch instagram.com directly → build_embed → send
  └─ path == p → fetch InstaFix proxy
       ├─ og:image /grid/ → _probe_instagram_images (concurrent) → carousel view
       └─ og:image /images/ → _resolve_instafix_image (single redirect) → dismiss view
```

See: `backend/discord/cogs/social_preview/cog.py`
