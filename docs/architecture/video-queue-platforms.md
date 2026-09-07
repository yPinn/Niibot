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
Clip (official APIs). Bilibili's metadata comes from an unofficial endpoint
that datacenter IPs frequently can't reach (risk-control `-412`), so its
duration is **best-effort** — the overlay must tolerate its absence (see
"End detection" below). Neither assumption holds for TikTok, which is why it
isn't supported yet (see "Deferred: TikTok" below).

## Three-layer model

| Layer          | Where                                                                                       | What differs per platform                                             |
| -------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| URL parsing    | `shared/video_sources.py`: `extract_*` functions, composed by `resolve_video_url()`         | Regex shape only                                                      |
| Metadata fetch | `shared/video_sources.py`: `fetch_*_info` functions, normalized by `fetch_video_metadata()` | API used, auth, whether duration/view_count are available at all      |
| Playback       | `frontend/.../videoQueueOverlay/players/{youtube,twitchClip,twitchVod,bilibili}.ts`         | Embed mechanism, and whether "video ended" is a real event or a guess |

Adding a platform means: one URL regex, one fetch function, one entry in the
`_WATCH_URL_BUILDERS` map (`video_sources.py`), and one `PlayerStrategy` in
`players/index.ts`. `resolve_video_url()` tries platforms in this order:
YouTube → Twitch Clip → Twitch VOD → Bilibili (including `b23.tv` short-link
redirects).

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

## Platform reference (parsing → metadata → playback)

|                                   | YouTube                                                                                                                                                                                | Twitch Clip                                                                                                  | Bilibili                                                                                                                                                                                                          |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Metadata API                      | YouTube Data API v3 (`videos.list`)                                                                                                                                                    | Twitch Helix `/helix/clips`                                                                                  | Public `x/web-interface/view` endpoint                                                                                                                                                                            |
| Official?                         | Yes                                                                                                                                                                                    | Yes                                                                                                          | **No** — not part of Bilibili's official Open Platform (that's a separate, application-gated program for content distribution). This is a reverse-engineered public endpoint with a spoofed Referer/User-Agent.   |
| Cost                              | Free, quota-based: 10,000 units/day default, `videos.list` costs 1 unit/call (~10k calls/day). No paid tier — exceeding quota requires Google's manual Audit and Quota Extension form. | Free, token-bucket rate limit: 800 points/min per client, most endpoints cost 1 point. No paid tier.         | Free today, but unauthorized use of an undocumented endpoint — no SLA, no rate-limit contract, can change format or start blocking without notice. Tracked as a standing technical-debt risk, not a one-time bug. |
| duration/view_count at queue time | Always (when API key configured)                                                                                                                                                       | Always                                                                                                       | **Best-effort** — unofficial endpoint, datacenter IPs frequently hit risk-control `-412`                                                                                                                          |
| Playback embed                    | YT IFrame API (`YT.Player`)                                                                                                                                                            | Signed source MP4 in a host `<video>` (resolve via private GraphQL); `clips.twitch.tv/embed` iframe fallback | Plain `<iframe>` — no control API                                                                                                                                                                                 |
| End detection                     | **Event-driven**: `onStateChange` ENDED + a polling fallback                                                                                                                           | **Event-driven** on the `<video>` path (`ended`); timer ceiling (90s) on the iframe fallback                 | **Timer-driven**: `setTimeout` from `duration_seconds`, else a 600s ceiling                                                                                                                                       |

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
