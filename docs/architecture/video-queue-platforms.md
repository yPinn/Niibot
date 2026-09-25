# Video Queue Platform Support

> Covers the platform registry introduced in `shared/video_sources.py`
> (`resolve_video_url` / `fetch_video_metadata` / `build_watch_url`) and the
> corresponding `players/` package under `frontend/src/pages/videoQueueOverlay/`.
> Read this before adding a new video source or changing how an existing one
> is parsed, fetched, or played back.

## Why this exists

Video Queue accepts a URL from chat (`!vq`), a channel-points redemption, or
the dashboard, and needs to (1) figure out which platform it's from, (2) fetch
its title/duration/view count, and (3) play it back in the OBS overlay with
automatic advance-on-end. Three call sites used to duplicate the same
detect-then-fetch cascade inline, with inconsistent return shapes between
platforms — that duplication is what `resolve_video_url()` /
`fetch_video_metadata()` collapse into one place. See
[api-endpoints.md](../reference/api-endpoints.md) for the `/api/video-queue`
routes that call into this layer.

Two things about video platforms are easy to assume are true for all of them
and are not: **every platform can tell you a video's duration before you play
it**, and **the video's total view count is available without the viewer
being logged in as its owner**. Both assumptions hold for YouTube and Twitch
Clip (official APIs). Bilibili has no official metadata API at all — the client
in `shared/bilibili_client.py` works around the risk control that answers a
datacenter IP with HTTP 412 (see "Bilibili metadata" below), but it can still
come back empty, so its duration is **best-effort** and the overlay must
tolerate its absence (see "End detection" below). Neither assumption holds for
TikTok, which is why it isn't supported yet (see "Deferred: TikTok" below).

## Three-layer model

| Layer          | Where                                                                                             | What differs per platform                                        |
| -------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| URL parsing    | `shared/video_sources.py`: `extract_*` functions, composed by `resolve_video_url()`               | Regex shape only                                                 |
| Metadata fetch | `shared/video_sources.py`: `fetch_*_info` functions, normalized by `fetch_video_metadata()`       | API used, auth, whether duration/view_count are available at all |
| Playback       | `frontend/.../videoQueueOverlay/players/{youtube,twitchClip,twitchVod,instagramReel,bilibili}.ts` | Embed mechanism, volume control, and end/error events            |

Adding a platform means: one URL regex, one fetch function, one entry in the
`_WATCH_URL_BUILDERS` map (`video_sources.py`), and one `PlayerStrategy` in
`players/index.ts`. `resolve_video_url()` tries platforms in this order:
YouTube → Twitch Clip → Twitch VOD → Instagram Reel (including `share/`
short-link redirects) → Bilibili (including `b23.tv` short-link redirects).

Every parser tokenizes the URL and validates an exact `http`/`https` hostname;
short-link redirects are followed manually and every hop is checked again.
Never reintroduce substring URL matching or automatic redirects here.

`shared/safe_urls.py` is where every submission source's raw text first gets
tokenized, so its tolerance is shared by all of them: chat, Channel Points
redemption, and the donation/dashboard forms. It strips straight/smart quotes
and the CJK quotation/title-mark brackets a pasted link commonly ends up
wrapped in (`「連結」`, `'https://…'`, `《…》`), plus zero-width/format
characters (U+200B, a stray BOM, …) a mobile keyboard or paste-from-app can
leave inside otherwise-correct text — invisible, so a viewer has no way to
notice or remove one before redeeming. None of this widens what counts as an
_allowed_ URL: trimming only ever shrinks the candidate token, and the exact
hostname check in `find_allowed_http_url()` / `parse_allowed_absolute_url()`
still runs on whatever's left (see `tests/shared/test_safe_urls.py`).

## Accepted URL shapes, and tracking-param hygiene

Only a platform's native id (and, for Twitch VOD/Bilibili, a `?t=`/`?p=`
value) is ever extracted from a submitted URL — everything else in the query
string is discarded, so `utm_*`, `si`, `igsh`, `spm_id_from`, and similar
share-tracking params never reach storage, a log line, or an outbound
request. The one place this needs active stripping rather than just not
reading a field is a short-link resolve that forwards a request upstream:
`resolve_bilibili_url()`'s `b23.tv` hop and `resolve_instagram_url()`'s
`/share/...` hop both drop the incoming query before making that request.

Recognized shapes per platform (all case-insensitive on path segments):

| Platform    | Hosts                                                                                   | Path shapes                                                                                       |
| ----------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| YouTube     | `youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtube-nocookie.com`, `youtu.be` | `/watch?v=`, `/shorts/{id}`, `/live/{id}`, `/embed/{id}`, `/v/{id}`, `youtu.be/{id}`              |
| Twitch Clip | `clips.twitch.tv`, `twitch.tv`, `m.twitch.tv`                                           | `clips.twitch.tv/{slug}`, `.../embed?clip={slug}`, `.../{channel}/clip/{slug}`, `.../clip/{slug}` |
| Twitch VOD  | `twitch.tv`, `m.twitch.tv`                                                              | `/videos/{id}[?t=1h2m3s]`                                                                         |
| Bilibili    | `bilibili.com`, `m.bilibili.com`, `b23.tv` (redirect)                                   | `/video/BV…[?p=N]`, `/video/av{aid}` (converted to BV), `b23.tv/{code}`                           |
| Instagram   | `instagram.com`, `instagr.am`                                                           | `/reel(s)/{code}`, `/p/{code}`, `/tv/{code}`, `/share/...` (redirect)                             |

Bilibili's multi-part (`分P`) videos are the one place a query value becomes
part of the stored identity rather than being discarded: `extract_bilibili_bvid()`
folds `?p=N` (N≥2) into the id itself as `BVxxxxxxxxxx_pN` — see "Bilibili
multi-part videos" below. `av{aid}` links are converted to their BV id via
`_av_to_bv()`, Bilibili's published (reverse-engineered) base58/XOR encoding —
deterministic, no network call.

## Submission-source policy

Submission source and video provider are separate axes. `VideoQueueAdmissionService`
owns the source policy; provider parsing and playback stay in the registry.

| Rule                                             | Chat | Channel Points            | Donate                    | Dashboard manual          |
| ------------------------------------------------ | ---- | ------------------------- | ------------------------- | ------------------------- |
| Video Queue enabled                              | Yes  | Yes                       | Yes                       | Yes                       |
| Source enabled                                   | —    | `redemption_enabled`      | Donate settings page      | Authenticated dashboard   |
| Playability + blocklist + global duration        | Yes  | Yes                       | Yes                       | Yes                       |
| Queue capacity + minimum views + replay cooldown | Yes  | Yes                       | Yes                       | No (broadcaster override) |
| Per-viewer limit + cooldown                      | Yes  | Yes                       | No stable Twitch identity | No                        |
| Source duration                                  | —    | `max_duration_redemption` | —                         | —                         |

When both the global duration and Channel Points duration are non-zero, the
shorter limit wins. Dashboard settings are intentionally ordered as Channel
Points → Donate → common rules → playback output → blocklist. Donate currently
accepts only YouTube at checkout, but its admitted item still passes the common
capacity, quality, duration, replay and blocklist gates.

Database defaults are: queue enabled, Channel Points enabled, Channel Points
maximum 600 seconds, queue capacity 20, no minimum views/per-viewer/cooldown/
global-duration/replay restriction, and output volume 100%.

Public queue reads remain unauthenticated for OBS. Queue advance and metadata
backfill require a per-channel overlay capability sent in `X-Overlay-Key`; the
dashboard URL keeps it in the fragment so it is not sent as an HTTP referrer.
Rotating the OBS URL immediately revokes the old capability. Preview mode is
always read-only, even if its URL contains a valid capability.

Admission emits one structured accepted/rejected log with source, channel and
reason/provider fields. Raw submitted URLs and requester text are intentionally
excluded from these outcome logs.

## Twitch VOD (`twitch.tv/videos/{id}`)

Added later, and one of the **best-behaved** of the five: Twitch's official embed
player JS API (`embed.twitch.tv` / `player.twitch.tv/js/embed/v1.js`) accepts a
`video` param — unlike clips — so `players/twitchVod.ts` gets a real player.
`autoplay` + `.play()` are imperative (OBS honours them, like YouTube's
`playVideo()`), `controls: false` hides the chrome, and the `ENDED` event gives
real end detection.

A VOD is hours long, so Video Queue treats it as a **long clip**:

- `extract_twitch_vod_info()` also parses the URL's `?t=1h2m3s` into
  `start_seconds` (a new `video_queue.start_seconds` column, migration 108).
- `fetch_video_metadata()` stores `duration_seconds =
min(TWITCH_VOD_WINDOW_SECONDS, vod_duration - start_seconds)` — the **capped
  play window**, not the VOD length. When Helix can't return the VOD duration
  (deleted / sub-only / expired) it falls back to the full window.
- The overlay seeks to `start_seconds + joinElapsed` and advances when
  `getCurrentTime() - start_seconds` reaches `duration_seconds`, or on `ENDED`.

`fetch_twitch_vod_info()` uses Helix `/videos` with the same app token as
clips; the duration string (`"3h20m5s"`) is parsed by `_parse_hms()`, shared
with the `?t=` parser.

## Instagram Reel (`instagram.com/reel/{shortcode}`)

Resolves through the same self-hosted **InstaFix** proxy the Discord bot's
social-preview cog already runs (`compose.yaml`'s `instafix` service —
see `docs/integrations/instafix.md`), via a new, deliberately minimal
`shared/instafix_client.py`. This is **not** the same code path as the
Discord cog's Instagram handling: that implementation also does
carousel/grid probing and profile enrichment that Video Queue doesn't need,
and consolidating the two into one shared client is a tracked follow-up
(see "Deferred" below), not done in this pass.

- `resolve_instagram_url()`/`extract_instagram_shortcode()` match a direct
  `/reel(s)/{shortcode}`, `/p/{shortcode}` (feed post), or `/tv/{shortcode}`
  (legacy IGTV, merged into feed video) URL on `instagram.com` or the
  `instagr.am` short domain, or follow the redirect on an
  `instagram.com/share/...` link (the mobile app's "Copy Link" output,
  stripped of its `igsh` tracking query before the request) to find the
  shortcode — same shape as `resolve_bilibili_url()`'s `b23.tv` handling.
  Every shape is stored as `video_type = "instagram_reel"`: InstaFix and the
  playback path are shortcode-keyed, not path-keyed, so a `/p/`- or
  `/tv/`-sourced entry plays back identically to a `/reel/`-sourced one.
- `fetch_instagram_reel_info()` doesn't know which of the four path shapes a
  shortcode came from (only the bare shortcode is threaded through
  `ResolvedVideo`), so its OpenGraph fetch tries InstaFix's `/reel/{code}/`
  proxy first, then `/p/{code}/` — mirroring `INSTAGRAM_PROXY_URL` in the
  Discord cog, which proxies whichever path type the original URL used.
- A `/p/` link isn't guaranteed to be a video — it's Instagram's general feed
  post shape, and can be a photo. `InstagramReelInfo.is_video` reports
  `True`/`False` only when the `/videos/{shortcode}/1` redirect positively
  resolved to something (`.mp4` or not); a redirect that merely failed to
  resolve leaves it `None` (unknown, not rejected — see "Playability
  precheck" below). `fetch_video_metadata()` rejects with
  `UNPLAYABLE_NOT_VIDEO` only on the positive `False` case.
- **Title** (`_extract_display_title()`) prefers the caption
  (`og:description`) over `@handle` — a caption actually describes the
  content, matching every other platform's title. It's cleaned first
  (`_strip_trailing_hashtags()`, duplicated from the Discord cog's version
  for the same staged-migration reason as the OG parser; embedded newlines
  collapsed to spaces) and capped at `_TITLE_MAX_LENGTH` (60 chars,
  deliberately short — it stands in for a title, not a caption display).
  Falls back to `@handle` when there's no usable caption (absent, or
  nothing left after stripping an all-hashtags caption). Creator matching does
  not depend on that title: the OG handle is stored separately as
  `creator_id`/`creator_name`. Instagram does not expose a stable numeric ID to
  this integration, so this provider's creator rule remains handle-based and
  can become stale after a rename.
- `fetch_instagram_reel_info()` fetches the Reel's title + thumbnail from
  InstaFix's OpenGraph page at **enqueue time**, concurrently with a second
  request that resolves the same `/videos/{shortcode}/1` redirect
  `fetch_instagram_reel_source()` uses at play time — not to reuse the mp4
  URL itself (it's signed and expires, so playback always re-resolves it
  fresh), but because the CDN URL's `efg` query param is an undocumented
  base64-encoded JSON blob that includes the real `duration_s`
  (`shared.instafix_client._extract_duration_seconds`). **View count is
  still permanently unavailable** — no field for it exists anywhere in
  InstaFix's response — but duration usually _is_ known at queue time now,
  same as YouTube/Twitch Clip. `metadata_best_effort = True` (same flag
  Bilibili uses) stays set because of view_count: `min_view_count` always
  skips rather than rejects an unwinnable submission, while the
  duration-cap gate now actually applies whenever the `efg` resolve
  succeeds, and only skips on the (rarer) case where that redirect fails —
  `metadata_gate_unverifiable()` already handles a present value correctly
  regardless of `best_effort`, so no gating-logic changes were needed to
  pick this up. When the redirect does fail, `duration_seconds` falls back
  to the pre-existing client-side backfill below.
- `is_vertical` tries the OG page's `og:video:width`/`height`
  (`shared.instafix_client._orientation_from_og`) first, but InstaFix's Reel
  OG page carries no such tags in practice, so this is almost always
  unknown. The real signal is `_orientation_from_mp4`: a bounded byte-range
  probe of the already-resolved mp4 CDN URL, parsed as an ISO-BMFF box tree
  (`moov` → `trak` → `tkhd`) for the video track's actual width/height —
  same "trust the asset, not unreliable metadata" approach
  `_extract_duration_seconds` takes with the `efg` param. Defaults to `True`
  only if both signals come back empty (network failure, or a `moov` that
  didn't fit the probed prefix). Most Reels are 9:16, but a landscape source
  video keeps its own aspect ratio when posted as a Reel, so only genuinely
  vertical entries get the blurred-side-column treatment
  (`current.is_vertical` in `VideoQueueOverlay.tsx`) — a landscape Reel
  plays plain, letterboxed like any other landscape source. Vertical YouTube
  and Instagram entries use one active centre player plus poster-only side
  panels. This avoids tripling SDK instances, network streams and decoders.
- **Playback**: identical mechanism to Twitch Clip's `<video>` path —
  `GET /api/video-queue/public/{u}/entries/{id}/reel-source` resolves the
  shortcode to a signed CDN mp4 URL fresh at play time (never cached; it
  expires) via `fetch_instagram_reel_source()`, then `players/
instagramReel.ts` plays it in a host `<video>` with real `ended` /
  `loadedmetadata` events. **Unlike Twitch Clip, there is no fallback embed**
  — Instagram has nothing equivalent to `clips.twitch.tv/embed` — so a
  resolve failure or a `<video>` `error` event skips the entry immediately
  instead of degrading to a lesser embed.
- `duration_seconds` is backfilled the same way Twitch Clip's is: once the
  resolved `<video>`'s `loadedmetadata` fires, `reportVideoMetadata` writes
  the real duration back for the dashboard/history.

## Platform reference (parsing → metadata → playback)

| Capability         | YouTube                                                                  | Twitch Clip                               | Twitch VOD                                                         | Instagram Reel                           | Bilibili                                                |
| ------------------ | ------------------------------------------------------------------------ | ----------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------- | ------------------------------------------------------- |
| Canonical identity | `youtube + video id`                                                     | `twitch_clip + slug`                      | `twitch_vod + VOD id`; timestamp stored separately                 | `instagram_reel + shortcode`             | `bilibili + BV id`; part N≥2 folded in as `_pN`         |
| Metadata           | Official Data API                                                        | Official Helix                            | Official Helix                                                     | Unofficial InstaFix; best-effort         | Unofficial web API; best-effort                         |
| Playback           | YT IFrame API                                                            | Signed MP4; iframe fallback               | Twitch Player API                                                  | Signed MP4; no fallback                  | Official embed iframe                                   |
| Gain `0..100`      | Yes (`setVolume`)                                                        | Yes on MP4; iframe is mute-only           | Yes (`setVolume`)                                                  | Yes (`video.volume`)                     | No; mute-only                                           |
| Start/end/error    | `PLAYING`, `ENDED`, `onError`, `onAutoplayBlocked`; 15s startup watchdog | `playing`/`ended`/`error`; fallback timer | `READY`, `PLAYING`, `ENDED`, `PLAYBACK_BLOCKED`; capped VOD window | `playing`/`ended`/`error`; failure skips | iframe `load`, best-effort ended message, timer ceiling |
| External SDK       | Lazy-loaded for this provider only                                       | None                                      | Lazy-loaded for this provider only                                 | None                                     | None                                                    |

Duplicate and replay keys are `(channel_id, video_type, video_id)`, so native
IDs that happen to be equal on different platforms do not collide. Twitch VOD
watch/history/requeue links preserve `start_seconds`.

All providers share a 15-second playback-start watchdog. Event-capable players
clear it only after actual playback and report a `confirmed` start; iframe
providers clear it on load and report a separately labelled `best_effort`
start before using their duration/timer ceiling. The write is idempotent per
queue entry and dashboard preview never sends it. Missing duration is therefore
bounded instead of stalling the queue indefinitely. The `!vq skip` command
remains the manual escape hatch.

`reportVideoMetadata` (`PATCH /api/video-queue/public/{username}/entries/{id}/metadata`)
is a capability-protected duration backfill path used by YouTube, Twitch Clip
and Instagram when duration was not known at enqueue time. Dashboard preview is
read-only and never reports metadata or advances the production queue.

## Autoplay and mute

`MountContext.muted` (`= isPreview`) and `volumePercent` are separate knobs.
OBS uses the configured gain; dashboard preview is always muted. YouTube and
Twitch VOD apply gain through official APIs. Host `<video>` paths use
`HTMLMediaElement.volume`. Twitch Clip's iframe fallback and Bilibili only
support a mute URL parameter, so their gain cannot be normalized.

Autoplay is not equally reliable across providers. Every controlled player
starts imperatively and reports actual playback; blocked/error paths advance
instead of waiting forever.

- **YouTube** calls `playVideo()` imperatively after `onReady` — an explicit
  command that bypasses the player's own autoplay heuristics. Works with sound
  in OBS, muted in preview.
- **Twitch clip** — the `clips.twitch.tv/embed` iframe cannot autoplay in OBS
  (Twitch gates unmuted autoplay on document visibility; OBS renders the page
  "hidden", so the clip mounts showing a centered play button and never starts;
  the `allow="autoplay 'src'"` experiment in #191 changed nothing and was
  reverted). `twitchClip.ts` therefore resolves the clip's **signed source
  MP4** and plays it in a host-controlled `<video>` — `video.play()` is
  imperative, like YouTube's `playVideo()`, so OBS's relaxed autoplay policy
  actually honours it, and it yields real `ended` / `timeupdate` events. The
  embed iframe stays as the fallback when the resolve fails.
  - Resolve path: `GET /api/video-queue/public/{u}/entries/{id}/clip-source` →
    `shared.video_sources.fetch_twitch_clip_source` → Twitch's **private
    GraphQL** endpoint (`ShareClipRenderStatus`, the call yt-dlp makes). This is
    a second Bilibili-tier unofficial dependency: the persisted-query hash
    rotates, the returned token is short-lived (resolved fresh at mount, never
    stored), the client id is yt-dlp's public one. On any failure the endpoint
    404s and the overlay uses the iframe.
  - The `<video>` loads directly from Twitch's clip CDN, so the overlay CSP
    (`frontend/public/_headers`) needs `media-src https://*.twitchcdn.net
https://clips-media-assets2.twitch.tv`; a media-src miss surfaces as a
    `<video>` error → iframe fallback.
- **Bilibili** uses `player.bilibili.com/player.html` — Bilibili's **official
  embed player** (its "share → embed" markup), built to be iframed on
  third-party sites. It was briefly swapped for `www.bilibili.com/blackboard/
html5mobileplayer.html` (56c4abd) to hide player chrome, but that mobile web
  player has heavier anti-embed checks and throws "本视频可能由于以下原因导致
  无法正常播放" inside an OBS Browser Source (fresh cookie jar, no `buvid3`).
  `&danmaku=0` still drops the bullet comments. `&muted=1` is appended **only**
  for the muted dashboard preview (an explicit `muted=0` made the player error).
  **Player chrome (top info bar, bottom control bar, centred "更高清" promo) stays
  visible in OBS — accepted, not a bug.** The official embed has no param to hide
  it, the "更高清" layer is always-on, and the hover-gated bars never fade because
  an OBS Browser Source sends the page no pointer events at all (so the
  `mouseleave` that starts the fade timer never fires). `pointerEvents: 'none'`
  on the iframe just keeps it in that state. A `#197` attempt to script a
  pause→play "nudge" into the idle state did nothing and was removed; the
  `enablejsapi=1` postMessage channel is kept only for the `ended` event.
  Bilibili has no `<video>` fallback — its stream URLs need `wbi` signing and
  residential IPs (rejected, see below). **If the official embed still fails in
  OBS, Bilibili is effectively browser/preview-only** and the queue should warn
  on submit rather than pretend it will play.

The dashboard preview is a **click-to-load poster** rather than an
always-mounted iframe: muted autoplay isn't reliable for every platform, and
the dashboard's "正在播放" card already carries live status, so the preview only
needs to answer "does the layout look right".

## Playability precheck (YouTube only)

Some videos load in the overlay but never actually play: YouTube's owner can
disable embedding, mark a video age-restricted (an embedded iframe has no
signed-in cookie to satisfy the gate), set it private, or the upload can be
deleted/rejected. The timer-based end detection still fires eventually, but the
viewer sees a dead frame until the ceiling expires.

`fetch_yt_info` requests the `status` part alongside `snippet,contentDetails,
statistics` and returns a `YouTubeInfo` dataclass carrying `playable: bool` and
`unplayable_reason` (`not_embeddable | age_restricted | private | removed`).
`_assess_yt_playability()` only trusts **positive** signals — a response with no
`status` block, an empty `items` array, a non-200, or a network error all leave
`playable = True` (fail-open), so a transient API problem never rejects a real
submission.

All four add paths — chat, Channel Points, Donate and dashboard — call the same
admission service. It checks playability immediately after metadata fetch and
before insertion. `min_view_count` and replay/capacity gates vary by source;
playability, global duration and blocklist do not, so the dashboard's
broadcaster-authority bypass does **not** skip them.

Twitch Clip always reports `playable = True` — clips always embed. Twitch VOD
(`invalid_timestamp`), Bilibili (`invalid_page`), and Instagram (`not_video`)
each add exactly one submission-time reason of their own, for an out-of-range
`?t=`/`?p=` or a `/p/` link that resolved to a photo post — Bilibili's general
metadata is otherwise too unreliable (`-412`) to gate on.

## Submission gates and best-effort metadata

The `min_view_count` and length-cap gates need a fetched value. When that value
is `None`, `VideoMetadata.metadata_best_effort` decides what "missing" means:

- **`False`** (YouTube, Twitch — official APIs): a `None` is a transient fetch
  failure. Sources that enforce the corresponding gate reject with a retryable
  message.
- **`True`** (Bilibili and Instagram — unofficial/best-effort metadata): a
  missing value may be normal and will not necessarily resolve on retry. The gate **skips**
  rather than rejecting — otherwise every Bilibili submission on a channel with
  any cap set is refused, and for a channel-points redemption the points are
  already spent with no refund path. The overlay's per-platform ceiling
  (`BILIBILI_MAX_SECONDS`) bounds playback instead. A Bilibili entry that _does_
  come back with a duration is still capped normally.

`shared.video_sources.metadata_gate_unverifiable(value, best_effort=...)` is the
single predicate; `fetch_video_metadata` sets `metadata_best_effort=True` for
Bilibili and Instagram Reel.

## Bilibili metadata (`shared/bilibili_client.py`)

Bilibili is not part of any official Open-Platform read API — every path here is
a reverse-engineered web endpoint with no SLA (same dependency class as the
Twitch clip GraphQL call). For a year Niibot sent a bare
`GET x/web-interface/view?bvid=…` with only a `Referer`; Bilibili's WAF now
answers that with **HTTP 412** from a container / datacenter egress IP, so
`duration` and `view_count` came back empty and every capped channel rejected
every Bilibili submission (fixed defensively — see "Submission gates" above).

`fetch_bilibili_video_data(bvid)` returns the raw `data` object (the
`x/web-interface/view` shape, also consumed by the Discord `social_preview`
cog) through three tiers, each a fallback for the one before:

1. **`x/web-interface/view`** (non-WBI) with a real Chrome `User-Agent`, a
   `.bilibili.com` `Referer`/`Origin`, a self-generated `buvid3` cookie
   (`f"{uuid4()}infoc"`, like yt-dlp — no `finger/spi` call), and a cached
   `bili_ticket` (a 3-day HMAC-signed JWT, `POST GenWebTicket`, that "lowers
   risk-control probability").
2. **`x/web-interface/wbi/view`** — same request plus a WBI `w_rid`/`wts`
   signature. `_MIXIN_KEY_ENC_TAB` is a constant Bilibili has not changed since
   WBI shipped in 2023; the daily `img_key`/`sub_key` come from
   `x/web-interface/nav` (or the `bili_ticket` response) and are cached ~1 h.
3. **Webpage scrape** — `GET https://www.bilibili.com/video/<bvid>`, read
   `window.__INITIAL_STATE__.videoData`. This is yt-dlp's primary path and the
   most 412-resistant.

Every tier fails open: exhaustion returns `None`, and the `metadata_best_effort`
handling keeps the video queueable. Credentials are cached at module scope as
plain strings, so they survive the throwaway `aiohttp` session that a caller
without a shared one creates. Reference vectors for the WBI mixin key / `w_rid`
and the `bili_ticket` HMAC are locked in `tests/shared/test_bilibili_client.py`.
No login (`SESSDATA`) — members-only / restricted videos stay unfetchable.

The `-412` risk is **reduced, not eliminated**: Bilibili can tighten any of
these at any time. If tier 3 also starts failing, the next step is routing
through the `scrapling` browser sidecar.

## Bilibili multi-part videos (`?p=`)

A single BV id can hold several parts (`分P` — a collection or a
multi-episode upload); the website's `?p=N` selects which one plays.
Video Queue folds that into the stored id rather than adding a DB column:

- `extract_bilibili_bvid()` returns `BVxxxxxxxxxx` for P1 (or no `?p=`) and
  `BVxxxxxxxxxx_pN` for `?p=N` with N≥2. P1 staying suffix-free means every
  row stored before multi-part support existed, and the common single-part
  case, are unaffected — `(video_type, video_id)` dedupe/blocklist/ranking
  keys still just work.
- `split_bilibili_id(video_id)` (backend) / `splitBilibiliId()` (frontend,
  `modules/videoQueue/utils.ts`) reverse it back to `(bvid, page)`. Every
  consumer of a stored Bilibili id — `fetch_video_metadata()`,
  `build_watch_url()`, the overlay's `players/bilibili.ts` (which passes
  `page=N` to the official embed) — splits first rather than assuming the id
  is a bare BV.
- `fetch_bilibili_info(bvid, page=N)` reads `data["pages"][N-1]` for that
  part's duration/dimension/title when the view endpoint's response included
  a `pages` list (it can be absent on a `-412`, same as everything else
  here). `page_count = len(pages)` when known, so a caller can tell "this
  part doesn't exist" (`page > page_count`, rejected with
  `UNPLAYABLE_INVALID_PAGE`) apart from "we don't know" (`page_count is
None`, not rejected).
- `_av_to_bv(aid)` runs before any of this: a pasted `/video/av{aid}` link
  is converted to its BV id first, then the same `?p=` folding applies.

## Thumbnails

`VideoMetadata.thumbnail_url` carries a poster image for the dashboard "now
playing" / "up next" cards (`NowPlayingCard.tsx`); it is stored on the row
(`video_queue.thumbnail_url`, migration 111) at INSERT and never updated. The
overlay does not use it.

- YouTube: `snippet.thumbnails` (`medium` → `high` → `default`).
- Twitch Clip: Helix `thumbnail_url`.
- Twitch VOD: Helix `thumbnail_url` with `%{width}x%{height}` → `320x180`.
- Bilibili: the view `data`'s `pic`, upgraded to `https://`.
- Instagram Reel: InstaFix's OG `image` path, resolved to a CDN URL at
  enqueue time (see "Instagram Reel" above).

`None` (Bilibili risk control, an unprocessed VOD, any fetch failure) just falls
back to a placeholder. The card also renders the placeholder on an `<img>`
`onError` — Bilibili's `i*.hdslb.com` CDN 403s a cross-site `Referer`, so the
`<img>` sends `referrerpolicy="no-referrer"`; if a host still blocks it the
error handler covers it. The dashboard CSP `img-src` (`frontend/public/_headers`)
allows `i.ytimg.com`, `*.hdslb.com`, `clips-media-assets2.twitch.tv`,
`static-cdn.jtvnw.net`, and `*.cdninstagram.com`.

## Creator identity

Migration 122 added `creator_id` and `creator_name` to queue/history rows.
Metadata normalization fills platform-native identity when available, and a
`kind='creator'` blocklist rule compares only `creator_id`; it never overloads
title or requester identity. Missing best-effort creator metadata fails open.

Migration 135 makes new `video` and `creator` rules provider-aware. Their
identity is `(video_type, value)` so equal native ids from different platforms
do not collide. Existing providerless rules remain deliberate wildcards during
the migration; keyword and user rules are always provider-neutral.

## Private playback rankings

The authenticated dashboard has a compact third workbench tab, `排行`, beside
`待播` and `紀錄`. It supports `本台／全站`, `7 日／30 日`, and provider filters.
Only rows with `playback_started_at` are qualified—queue promotion alone is not
a play. Channel rankings order by play count; global rankings order by distinct
channel count and then play count. The global response contains aggregate
counts only, never channel ids or requester identity. Existing terminal rows
are intentionally not backfilled from `started_at`, so the chart begins with
verifiable playback facts collected after migration 135.

Each row can be added back to the queue, opened at its provider URL, or blocked
for the current channel by provider-scoped video/creator identity. Twitch VOD
rows retain the representative `start_seconds`, so an action does not silently
drop the segment offset. The first release deliberately excludes public charts,
all-time/trending formulas, autoplay-fill, and batch add.

## Deferred: Instagram client consolidation

`shared/instafix_client.py` (Video Queue) and `discord/cogs/social_preview/`
(Discord link previews) are currently **two independent implementations**
against the same self-hosted InstaFix instance — the Video Queue client was
deliberately written fresh and minimal rather than refactored out of the
Discord cog, to keep that change reviewable and avoid touching the cog's
already-production-tested carousel/grid/profile-enrichment logic in the
same pass. Consolidating them into one shared client (probably living in
`shared/` and covering the union of both call shapes) is a reasonable
follow-up once the Video Queue path has run in production for a while, not
a correctness requirement.

## Deferred: donation path multi-platform support

Donation checkout still stores `youtube_video_id`, so the public form is
YouTube-only. After payment, `_enqueue_donated_video()` now goes through the
same admission service as every other source, including common capacity,
minimum-view, duration, replay, playability and blocklist checks. A rejected
paid media item is logged but never rolls back the already-settled payment.

To pick this up:

- Replace the persisted checkout field with a provider-neutral URL and resolve
  it through the registry before payment.
- `frontend/src/pages/DonatePage.tsx` names its field `youtubeUrl` /
  `youtube_url` and its placeholder says "YouTube 連結（選填）" — both need to
  go generic, mirroring the `VideoQueue.tsx` dashboard input fix already made
  for the same reason.
- Preserve the current common-gate policy unless the product explicitly
  introduces a separate paid-media override.

## Deferred: TikTok

TikTok has no official channel that returns metadata for an arbitrary public
video someone else posted:

| Official channel                           | Usable here?  | Why not                                                                                                |
| ------------------------------------------ | ------------- | ------------------------------------------------------------------------------------------------------ |
| oEmbed (`tiktok.com/oembed`)               | Partial       | No `duration`, no `view_count` — only title/author/thumbnail                                           |
| Embed Player (`tiktok.com/player/v1/{id}`) | Playback only | Real event-driven player (`onStateChange`, `onCurrentTime`) — good for playback, but still no metadata |
| Display API                                | No            | Only returns the _authenticated user's own_ videos, not arbitrary links                                |
| Research API                               | No            | Restricted to verified academic/public-interest institutions as of 2026                                |

Unlike YouTube/Twitch Clip/Bilibili, TikTok cannot supply `duration_seconds`
before the video plays. That breaks the assumption `startTimerBasedEnd()`
relies on — but TikTok's Embed Player is event-driven like YouTube's (real
`onStateChange`/`ended` events, `onCurrentTime` giving live duration), so it
would use the _other_ end-detection strategy, plus the existing
`reportVideoMetadata` duration-backfill mechanism (today a YouTube fallback
for quota failures) would become TikTok's **primary** and only source of
duration — never known at queue time, only once the viewer's player reports
it.

Two things need deciding before implementation, not just building:

1. **`min_view_count` cannot apply to TikTok.** There is no accessible
   view-count source for a viewer-submitted link. Either the setting silently
   doesn't filter TikTok entries, or TikTok submissions are rejected outright
   on any channel with `min_view_count > 0` — this is a product call.
2. **The registry needs a capability axis it doesn't have yet.** Today
   `VideoMetadata`/`PlayerStrategy` assume every platform behaves alike
   (duration known upfront, `requiresApi` is the only playback variable).
   TikTok is the first platform where that stops being true, so it's also the
   right moment to add explicit capability flags (e.g. `has_view_count`,
   `end_detection: 'event' | 'timer'`) — not before, since a flag with only
   one possible value across all current platforms would be speculative
   design with no real caller to validate it against.
