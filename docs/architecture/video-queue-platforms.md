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

| Layer          | Where                                                                                       | What differs per platform                                             |
| -------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| URL parsing    | `shared/video_sources.py`: `extract_*` functions, composed by `resolve_video_url()`         | Regex shape only                                                      |
| Metadata fetch | `shared/video_sources.py`: `fetch_*_info` functions, normalized by `fetch_video_metadata()` | API used, auth, whether duration/view_count are available at all      |
| Playback       | `frontend/.../videoQueueOverlay/players/{youtube,twitchClip,twitchVod,bilibili}.ts`         | Embed mechanism, and whether "video ended" is a real event or a guess |

Adding a platform means: one URL regex, one fetch function, one entry in the
`_WATCH_URL_BUILDERS` map (`video_sources.py`), and one `PlayerStrategy` in
`players/index.ts`. `resolve_video_url()` tries platforms in this order:
YouTube → Twitch Clip → Twitch VOD → Instagram Reel (including `share/`
short-link redirects) → Bilibili (including `b23.tv` short-link redirects).

## Twitch VOD (`twitch.tv/videos/{id}`)

Added later, and the **best-behaved** of the four: Twitch's official embed
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
social-preview cog already runs (`docker-compose.yml`'s `instafix` service —
see `docs/integrations/instafix.md`), via a new, deliberately minimal
`shared/instafix_client.py`. This is **not** the same code path as the
Discord cog's Instagram handling: that implementation also does
carousel/grid probing and profile enrichment that Video Queue doesn't need,
and consolidating the two into one shared client is a tracked follow-up
(see "Deferred" below), not done in this pass.

- `resolve_instagram_url()` matches a direct `/reel(s)/{shortcode}` URL, or
  follows the redirect on an `instagram.com/share/...` link (the mobile
  app's "Copy Link" output) to find the shortcode — same shape as
  `resolve_bilibili_url()`'s `b23.tv` handling.
- **Title** (`_extract_display_title()`) prefers the caption
  (`og:description`) over `@handle` — a caption actually describes the
  content, matching every other platform's title. It's cleaned first
  (`_strip_trailing_hashtags()`, duplicated from the Discord cog's version
  for the same staged-migration reason as the OG parser; embedded newlines
  collapsed to spaces) and capped at `_TITLE_MAX_LENGTH` (60 chars,
  deliberately short — it stands in for a title, not a caption display).
  Falls back to `@handle` when there's no usable caption (absent, or
  nothing left after stripping an all-hashtags caption). **Known trade-off**:
  this removes the one place a Reel's handle lived in stored `title` data,
  so a `VideoQueueBlocklistRepository` `kind='creator'` entry matching by
  Instagram handle would no longer hit reliably — see "Deferred: creator
  identity normalization" below.
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
- `is_vertical` is detected from the OG page's `og:video:width`/`height`
  (`shared.instafix_client._extract_is_vertical`), defaulting to `True`
  when those tags are missing or unreadable. Most Reels are 9:16, but a
  landscape source video keeps its own aspect ratio when posted as a Reel,
  so only genuinely vertical entries get the blurred-side-column treatment
  (`current.is_vertical` in `VideoQueueOverlay.tsx`) — a landscape Reel
  plays plain, letterboxed like any other landscape source. Unlike
  `players/youtube.ts`'s `createSidePlayer`
  (full separate `YT.Player` instances with an all-ready barrier and
  state-change sync), `players/instagramReel.ts`'s side panels are just two
  more `<video>` elements pointing at the same resolved mp4 URL — no
  player-object abstraction to juggle, just `currentTime`/`play()` nudged
  back in sync (>0.3s drift) off the center video's once-a-second progress
  tick. `players/shared.ts`'s `destroyAllPlayers()` gained an explicit
  `sideContainerRefs` cleanup param for this — YouTube's side `YT.Player`s
  self-clean via `.destroy()`, but a bare `<video>` element has nothing
  equivalent, so leaving the old one in place would leak into the next mount.
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

|                                   | YouTube                                                                                                                                                                                | Twitch Clip                                                                                                  | Instagram Reel                                                                                                                                                              | Bilibili                                                                                                                                                                                                          |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Metadata API                      | YouTube Data API v3 (`videos.list`)                                                                                                                                                    | Twitch Helix `/helix/clips`                                                                                  | `shared/instafix_client.py` via the self-hosted InstaFix proxy — OpenGraph tags only                                                                                        | `shared/bilibili_client.py`: `x/web-interface/view` → WBI `wbi/view` → webpage `__INITIAL_STATE__` (see "Bilibili metadata")                                                                                      |
| Official?                         | Yes                                                                                                                                                                                    | Yes                                                                                                          | **No** — InstaFix is a self-hosted reverse-engineered proxy, not part of Instagram's Graph API                                                                              | **No** — not part of Bilibili's official Open Platform (that's a separate, application-gated program for content distribution). This is a reverse-engineered public endpoint with a spoofed Referer/User-Agent.   |
| Cost                              | Free, quota-based: 10,000 units/day default, `videos.list` costs 1 unit/call (~10k calls/day). No paid tier — exceeding quota requires Google's manual Audit and Quota Extension form. | Free, token-bucket rate limit: 800 points/min per client, most endpoints cost 1 point. No paid tier.         | Free, self-hosted — no SLA, no rate-limit contract; the same dependency class as Bilibili                                                                                   | Free today, but unauthorized use of an undocumented endpoint — no SLA, no rate-limit contract, can change format or start blocking without notice. Tracked as a standing technical-debt risk, not a one-time bug. |
| duration/view_count at queue time | Always (when API key configured)                                                                                                                                                       | Always                                                                                                       | Duration: **usually** — decoded from an undocumented CDN URL param, see above; falls back to client-side backfill on failure. View count: **never**, no field exists at all | **Best-effort** — unofficial endpoint, datacenter IPs frequently hit risk-control `-412`                                                                                                                          |
| Playback embed                    | YT IFrame API (`YT.Player`)                                                                                                                                                            | Signed source MP4 in a host `<video>` (resolve via private GraphQL); `clips.twitch.tv/embed` iframe fallback | Signed source MP4 in a host `<video>` (resolve via InstaFix); **no fallback embed exists**                                                                                  | Plain `<iframe>` — no control API                                                                                                                                                                                 |
| End detection                     | **Event-driven**: `onStateChange` ENDED + a polling fallback                                                                                                                           | **Event-driven** on the `<video>` path (`ended`); timer ceiling (90s) on the iframe fallback                 | **Event-driven** (`ended`) — always, since there's no timer-based iframe path to fall back to                                                                               | **Timer-driven**: `setTimeout` from `duration_seconds`, else a 600s ceiling                                                                                                                                       |

The event-driven vs. timer-driven split is the one piece of platform-specific
_behavior_ the frontend registry does not (and should not) paper over: YouTube
mounts a real player object and reacts to its actual state; the Twitch clip and
Bilibili iframes have no such signal and instead trust the server-reported
`duration_seconds` to schedule `handleVideoEnd` themselves
(`players/shared.ts`'s `startTimerBasedEnd()`). When `duration_seconds` is
missing — always a risk for Bilibili — that helper falls back to a per-platform
ceiling (`CLIP_MAX_SECONDS` / `BILIBILI_MAX_SECONDS`) so the queue always
advances instead of stalling forever on one failed metadata fetch. The tradeoff
is a Bilibili entry with no duration runs to the ceiling (or is cut short if it
is longer), and its progress bar / countdown read `--:--`. The `!vq skip`
command is the manual escape hatch. See the TikTok section below for the harder
case where duration is _never_ knowable at queue time.

`reportVideoMetadata` (`PATCH /api/video-queue/public/{username}/metadata/{id}`)
is the duration backfill path: the YouTube strategy already calls it from
`onReady` when the Data API returned null. A Bilibili equivalent (reading
duration off the `html5mobileplayer` iframe via `postMessage`) is possible but
deferred — the ceiling covers the "queue must not stall" requirement, and this
would only improve timing precision.

## Autoplay and mute

`MountContext.muted` (currently `= isPreview`) is the one knob: the OBS overlay
plays **with sound** (OBS's mixer owns page audio), the dashboard preview must
be **muted**. YouTube takes `mute` as a `playerVars` value; the Twitch clip and
Bilibili plain iframes have no host-side mute (an `<iframe>` isn't a `<video>`),
so it must be a player-URL param — `muted=<bool>` on both
`clips.twitch.tv/embed` and `player.bilibili.com/player.html`.

Autoplay is not equally reliable across the three. **Confirmed by OBS testing:
only YouTube autoplays with sound in an OBS Browser Source.**

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

All three add paths — chat `!vq` (`video_queue.py`), channel-points redemption
(`channel_points.py`), and the dashboard `POST /entries`
(`video_queue_router.py`, raising `VideoNotPlayableError` → 422) — check
`metadata.playable` right after the metadata fetch and reject with
`unplayable_message(reason)` before inserting. `min_view_count` and the
duration caps are policy toggles; playability is not, so the dashboard's
broadcaster-authority bypass does **not** skip it.

Twitch Clip and Bilibili always report `playable = True`: clips always embed,
and Bilibili's metadata is already too unreliable (`-412`) to gate on.

## Submission gates and best-effort metadata

The `min_view_count` and length-cap gates need a fetched value. When that value
is `None`, `VideoMetadata.metadata_best_effort` decides what "missing" means:

- **`False`** (YouTube, Twitch — official APIs): a `None` is a transient fetch
  failure. All three add paths (chat `!vq`, redemption, dashboard `POST
/entries`) reject with a "請稍後再試" message so the requester can retry.
- **`True`** (Bilibili — the unofficial `-412` endpoint): a `None` is the normal
  state from a datacenter IP and will not resolve on retry. The gate **skips**
  rather than rejecting — otherwise every Bilibili submission on a channel with
  any cap set is refused, and for a channel-points redemption the points are
  already spent with no refund path. The overlay's per-platform ceiling
  (`BILIBILI_MAX_SECONDS`) bounds playback instead. A Bilibili entry that _does_
  come back with a duration is still capped normally.

`shared.video_sources.metadata_gate_unverifiable(value, best_effort=...)` is the
single predicate; `fetch_video_metadata` sets `metadata_best_effort=True` only
on the Bilibili branch.

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

## Deferred: creator identity normalization

`VideoQueueBlocklistRepository.check()`'s `kind='creator'`/`'user'`
blocklist entries match against whatever happens to live in `title`
(and `requested_by`, the _submitter_, not necessarily the _creator_) — there
is no normalized, platform-independent "who made this content" field.
YouTube's `title` is the video's title, not the channel name; Twitch Clip's
`requested_by` may read as the broadcaster but the clip's actual creator is
a separate Helix field never surfaced to the queue row; Bilibili and
Instagram each have their own shape too. This was always latent, but became
concrete when Instagram's `title` switched from `@handle` to the caption
(see "Instagram Reel" above) — removing the one place a Reel's handle
happened to live in queue data.

No Instagram creator-blocklist entries can exist yet (the platform just
shipped), so nothing regresses today, but this needs a real fix — likely a
dedicated `creator` field per platform, not another field overloaded to
double as identity — before creator-based blocklist/filter features can be
trusted to work consistently across platforms. Flagged for full research,
not scoped or started.

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

`backend/api/routers/donation_router.py` only imports `extract_youtube_info`
(not the full registry) and `_enqueue_donated_video()` calls
`VideoQueueRepository.add()` without passing `video_type`, relying on the
repository's `"youtube"` default. This was an intentional scope cut when the
platform registry was introduced — donation was left untouched to keep that
change reviewable, not because Twitch Clip/Bilibili donations are unwanted.

To pick this up:

- Switch `donation_router.py` to `resolve_video_url()` / `fetch_video_metadata()`
  and pass `video_type` explicitly to `repo.add()`.
- `frontend/src/pages/DonatePage.tsx` names its field `youtubeUrl` /
  `youtube_url` and its placeholder says "YouTube 連結（選填）" — both need to
  go generic, mirroring the `VideoQueue.tsx` dashboard input fix already made
  for the same reason.
- Decide whether donation should carry the same `min_view_count` /
  duration limits as redemption, or bypass them the way the dashboard does —
  this is a product decision, not a technical one.

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
