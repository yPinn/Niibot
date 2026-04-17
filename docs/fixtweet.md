# FixTweet / FxEmbed — Self-Hosted X/Twitter OG Proxy

## What It Is

[FixTweet/FxTwitter](https://github.com/FixTweet/FxTwitter) (a.k.a. FxEmbed) is a Cloudflare Workers service
that returns OG-tagged HTML for X/Twitter posts, enabling Discord (and other clients) to embed tweets with proper
images, videos, and multi-image mosaics.

**Supported platforms:** X/Twitter · Bluesky · Mastodon · TikTok
**NOT supported (as of 2026-04):** Threads — [issue #1441](https://github.com/FixTweet/FxTwitter/issues/1441) open, no ETA

---

## Self-Hosting (Cloudflare Workers)

**Prerequisites:** Node.js, Cloudflare account (free tier: 100k req/day)

```bash
git clone https://github.com/FixTweet/FxTwitter
cd FxTwitter
cp wrangler.example.toml wrangler.toml   # add your Cloudflare account_id
cp .env.example .env                      # configure domains
npm install
npx wrangler login
npm run deploy
```

### Key `wrangler.toml` fields

```toml
name = "fxembed"                          # Worker name → subdomain: fxembed.{account}.workers.dev
compatibility_date = "2026-04-11"
main = "./dist/worker.js"

[build]
command = "npm run build"
```

### Key `.env` fields

```env
# Domains served by this worker (set after deploying to know your workers.dev URL)
STANDARD_DOMAIN=fxtwitter.example.com
DIRECT_MEDIA_DOMAIN=d.fxtwitter.example.com
TEXT_ONLY_DOMAIN=t.fxtwitter.example.com
GALLERY_DOMAIN=g.fxtwitter.example.com
MOSAIC_DOMAIN=m.fxtwitter.example.com
```

### Secrets (optional)

```bash
npx wrangler secret put CREDENTIAL_KEY          # auth encryption key
npx wrangler secret put EXCEPTION_DISCORD_WEBHOOK  # error reporting
```

---

## URL Patterns

Replace the original domain with your self-hosted domain (or use the public endpoints).

### X/Twitter

| Intent                        | URL format                                      |
| ----------------------------- | ----------------------------------------------- |
| Standard embed                | `https://{host}/{username}/status/{tweet_id}`   |
| Direct media (no embed)       | `https://d.{host}/{username}/status/{tweet_id}` |
| Mosaic (multi-image combined) | `https://m.{host}/{username}/status/{tweet_id}` |
| Text-only embed               | `https://t.{host}/{username}/status/{tweet_id}` |
| Gallery view                  | `https://g.{host}/{username}/status/{tweet_id}` |

Public fallback domains (no self-hosting needed for testing):
`fxtwitter.com` · `fixupx.com` · `vxtwitter.com`

---

## OG Tag Structure

FxEmbed returns standard HTML with these meta tags:

```html
<meta property="og:title" content="Display Name (@handle)" />
<meta property="og:description" content="tweet text..." />
<meta property="og:image" content="https://pbs.twimg.com/..." />
<meta property="og:url" content="https://x.com/..." />
<meta property="og:site_name" content="FixTweet" />
<!-- customisable -->
<meta property="og:type" content="video.other" />
<!-- if video -->

<!-- Video embed -->
<meta name="twitter:card" content="player" />
<meta name="twitter:player" content="https://..." />
<meta name="twitter:player:width" content="1280" />
<meta name="twitter:player:height" content="720" />
```

**Single image:** `twitter:card` = `summary_large_image`
**Video:** `twitter:card` = `player` — use `twitter:player` for the stream URL
**Multiple images:** `m.` prefix domain requests a mosaic (combined JPEG); single `og:image`

---

## User-Agent Behaviour

FxEmbed **auto-detects** embedding clients (Discord, Telegram, iMessage) from the `User-Agent` header and
returns OG-optimised HTML for them.

```python
# Niibot: use the default client UA — FxEmbed will detect Discord's crawler UA
headers = {"User-Agent": "Discordbot/2.0"}

# Or let the HTTP client use its default; FxEmbed handles both
```

Unlike InstaFix, no redirect-on-wrong-UA issue — FxEmbed always returns HTML.

---

## Multi-Image (Mosaic)

FxEmbed combines up to 4 images into a single mosaic JPEG when the `m.` subdomain is used.

```text
m.fxtwitter.com/{username}/status/{id}
→ og:image = https://mosaic.fxtwitter.com/jpeg/{id}/{media_id_1}/{media_id_2}/...
```

For Niibot embed usage, the standard domain is sufficient — Discord displays the first image via `og:image`;
the mosaic domain is useful when you want all images in one embed image.

---

## Integration Pattern (for Niibot)

```text
on_message → TWITTER_RE match → _handle_twitter
  └─ fetch https://{FIXTWEET_HOST}/{username}/status/{id}
       ├─ parse OG tags (standard _parse_og)
       └─ build embed:
            author_name = og:title (contains "@handle")
            description = og:description
            image_url   = og:image
            url         = og:url (links back to x.com)
```

### Constants

```python
FIXTWEET_HOST = os.getenv("FIXTWEET_HOST", "fxtwitter.com")   # or self-hosted domain
TWITTER_RE = re.compile(
    r"https?://(?:www\.)?(?:twitter|x)\.com/(\w+)/status/(\d+)",
    re.IGNORECASE,
)
```

### Fetch

```python
proxy_url = f"https://{FIXTWEET_HOST}/{username}/status/{tweet_id}"
og = await self._fetch_og(proxy_url, bot_ua=True)
```

No redirect-follow needed — FxEmbed returns 200 with HTML directly.

---

## Deployment Notes

- **Free tier** covers typical bot usage (100k req/day per Cloudflare account)
- Workers URL before custom domain: `https://{name}.{account}.workers.dev`
- Set `FIXTWEET_HOST` env var on the discord-bot container to point at your Worker URL
- No Docker container needed — runs entirely on Cloudflare's edge

---

## Threads Status

Threads is **not supported** by FxEmbed (as of April 2026). Tracking issue: [FixTweet/FxTwitter#1441](https://github.com/FixTweet/FxTwitter/issues/1441).

For Threads, alternative approaches:

- Direct OG scrape with rotating proxy (unreliable — Meta login wall)
- Official Threads API (requires user OAuth, not suitable for server-level bot)
- Watch for community forks if/when the FixTweet team adds support
