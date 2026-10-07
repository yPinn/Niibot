import type { VideoQueueLiveInsert } from '@/api/videoQueue'

import { reportHlsFailure } from './hlsDiagnostics'
import { makeMountDiv } from './shared'
import { loadTwitchEmbedAPI } from './twitchVod'
import type { TwitchPlayerInstance, YTPlayer } from './types'

// Live insert (直播播放): the broadcaster plays someone's ongoing live stream
// open-ended — background music, a watch-along — instead of the queue. Unlike
// a queue entry there is no duration, no countdown and no advance: it plays
// until the broadcaster stops it (the row disappears from the stream) or the
// stream itself ends, which the player reports here exactly once.
//
// Ending is detected from player events only — never by polling our API or
// Helix (see the Cloudflare request budget in docs/guides/cloudflare-pages.md).
//
// Twitch: the embed player will not autoplay in an OBS Browser Source (it sits
// on a play button, even in OBS "Interact" — confirmed on staging), same as the
// clip embed. So the stream plays in a host-controlled <video> via hls.js from
// a signed playlist the backend resolves (/insert/playlist.m3u8); the embed stays as
// the fallback when that can't start. YouTube's player autoplays fine.
//
// The backend relays the variant playlists too (Twitch 403s them for any
// non-Twitch Origin), pointing them at the direct API host so the ~2 s variant
// polling skips the Pages proxy — see "例外：直播插播 HLS" in
// docs/guides/cloudflare-pages.md. Segments still come straight from Twitch.

/** Twitch fires OFFLINE on a brief broadcaster disconnect too; only end once it
 *  has stayed offline this long (an ONLINE in between cancels). */
export const OFFLINE_GRACE_MS = 60_000
/** HLS: after a fatal error mid-stream, re-resolve this often within the grace. */
export const HLS_RETRY_MS = 15_000

export type LiveInsertEndReason = 'ended' | 'offline' | 'provider_error'

export interface LiveInsertController {
  setVolume(volumePercent: number, muted: boolean): void
  destroy(): void
}

export interface LiveInsertMountOptions {
  insert: VideoQueueLiveInsert
  container: HTMLDivElement
  muted: boolean
  onEnded: (reason: LiveInsertEndReason) => void
  /** Twitch: resolve a direct HLS playlist URL; null/absent → embed player. */
  resolveTwitchSource?: () => Promise<string | null>
}

function mountTwitchEmbed({
  insert,
  container,
  muted,
  onEnded,
}: LiveInsertMountOptions): LiveInsertController | null {
  const Player = window.Twitch?.Player
  if (!Player) return null

  const player: TwitchPlayerInstance = new Player(makeMountDiv(container), {
    channel: insert.source_id,
    parent: [window.location.hostname],
    width: '100%',
    height: '100%',
    autoplay: true,
    muted,
    controls: false,
  })

  let volume = insert.volume_percent
  let isMuted = muted
  const apply = () => {
    player.setVolume(volume / 100)
    player.setMuted(isMuted || volume === 0)
  }
  apply()
  if (Player.READY) player.addEventListener(Player.READY, apply)

  let offlineTimer: ReturnType<typeof setTimeout> | null = null
  const clearOffline = () => {
    if (offlineTimer) clearTimeout(offlineTimer)
    offlineTimer = null
  }
  if (Player.OFFLINE) {
    player.addEventListener(Player.OFFLINE, () => {
      if (!offlineTimer) offlineTimer = setTimeout(() => onEnded('offline'), OFFLINE_GRACE_MS)
    })
  }
  if (Player.ONLINE) player.addEventListener(Player.ONLINE, clearOffline)
  player.addEventListener(Player.ENDED, () => onEnded('ended'))
  // Belt-and-braces autoplay nudge (harmless if already playing), as for VODs.
  const playTimer = setTimeout(() => {
    try {
      player.play()
    } catch {
      /* ignore */
    }
  }, 500)

  return {
    setVolume(nextVolume, nextMuted) {
      volume = nextVolume
      isMuted = nextMuted
      apply()
    },
    destroy() {
      clearTimeout(playTimer)
      clearOffline()
      try {
        player.destroy()
      } catch {
        /* ignore */
      }
    },
  }
}

function mountYouTube({
  insert,
  container,
  muted,
  onEnded,
}: LiveInsertMountOptions): LiveInsertController | null {
  if (!window.YT?.Player) return null

  let volume = insert.volume_percent
  let isMuted = muted
  let ready = false
  const apply = (target: YTPlayer) => {
    target.setVolume(volume)
    if (isMuted || volume === 0) target.mute()
    else target.unMute()
  }

  const player: YTPlayer = new window.YT.Player(makeMountDiv(container), {
    width: '100%',
    height: '100%',
    videoId: insert.source_id,
    // Start muted while the iframe initializes; onReady applies the real state
    // and starts playback imperatively (same as queue YouTube entries).
    playerVars: { autoplay: 0, controls: 0, rel: 0, iv_load_policy: 3, mute: 1 },
    events: {
      onReady: event => {
        ready = true
        apply(event.target)
        event.target.playVideo()
      },
      onStateChange: event => {
        if (event.data === 0) onEnded('ended') // YT.PlayerState.ENDED — the broadcast ended
      },
      onError: () => onEnded('provider_error'),
    },
  })

  return {
    setVolume(nextVolume, nextMuted) {
      volume = nextVolume
      isMuted = nextMuted
      if (ready) apply(player)
    },
    destroy() {
      try {
        player.destroy()
      } catch {
        /* ignore */
      }
    },
  }
}

/** `play()` returns a promise in browsers; never let a rejection (or a test DOM
 *  without media support) escape — failures surface through hls.js / events. */
function safePlay(video: HTMLVideoElement) {
  try {
    void video.play()?.catch(() => {})
  } catch {
    /* ignore */
  }
}

interface HlsHandle {
  destroy(): void
}

/**
 * Play the HLS playlist in `video`. `onStartFailed` fires when it never got
 * going (→ caller falls back to the embed); `onLost` when a stream that was
 * playing hits a fatal error (→ caller retries, then ends).
 */
async function mountHls(
  url: string,
  container: HTMLDivElement,
  video: HTMLVideoElement,
  handlers: { onStartFailed: () => void; onLost: () => void }
): Promise<HlsHandle> {
  const { default: Hls } = await import('hls.js')
  let started = false
  let failed = false
  const onPlaying = () => (started = true)
  const fail = () => {
    if (failed) return
    failed = true
    if (started) handlers.onLost()
    else handlers.onStartFailed()
  }
  container.innerHTML = ''
  container.appendChild(video)
  video.addEventListener('playing', onPlaying)

  if (!Hls.isSupported()) {
    if (!video.canPlayType('application/vnd.apple.mpegurl')) {
      fail()
      return { destroy: () => video.removeEventListener('playing', onPlaying) }
    }
    video.src = url // native HLS (Safari) — not OBS, but harmless
    video.addEventListener('error', fail, { once: true })
    safePlay(video)
    return {
      destroy: () => {
        video.removeEventListener('playing', onPlaying)
        video.removeAttribute('src')
      },
    }
  }

  // No worker: the overlay CSP allows no blob: scripts, and one stream doesn't
  // need it. Cap to the player size — the overlay is ~632×353, so OBS decodes
  // 360p/480p instead of source quality.
  const hls = new Hls({ enableWorker: false, capLevelToPlayerSize: true })
  hls.on(Hls.Events.ERROR, (_event, data) => {
    if (!data.fatal) return
    reportHlsFailure('twitch_live', data, started ? 'playing' : 'start')
    fail()
  })
  // play() before any data can reject silently; ask again once it can play.
  video.addEventListener('canplay', () => {
    if (video.paused) safePlay(video)
  })
  hls.loadSource(url)
  hls.attachMedia(video)
  safePlay(video)
  return {
    destroy: () => {
      video.removeEventListener('playing', onPlaying)
      hls.destroy()
    },
  }
}

function mountTwitch(options: LiveInsertMountOptions): LiveInsertController {
  const { insert, container, onEnded, resolveTwitchSource } = options
  let volume = insert.volume_percent
  let muted = options.muted
  let destroyed = false
  let embed: LiveInsertController | null = null
  let hls: HlsHandle | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let lostSince: number | null = null

  const video = document.createElement('video')
  video.autoplay = true
  video.playsInline = true
  video.volume = volume / 100
  video.muted = muted || volume === 0
  video.style.cssText = 'width:100%;height:100%;object-fit:contain;background:#000'
  video.addEventListener('playing', () => (lostSince = null))
  video.addEventListener('ended', () => onEnded('ended'))

  const fallBackToEmbed = () => {
    hls?.destroy()
    hls = null
    video.remove()
    loadTwitchEmbedAPI()
      .then(() => {
        if (destroyed) return
        embed = mountTwitchEmbed({
          ...options,
          insert: { ...insert, volume_percent: volume },
          muted,
        })
      })
      .catch(() => {})
  }

  // A stream that was playing and fails is re-resolved every HLS_RETRY_MS (a
  // brief broadcaster disconnect recovers); after OFFLINE_GRACE_MS it has ended.
  const retry = () => {
    if (destroyed) return
    lostSince ??= Date.now()
    if (Date.now() - lostSince >= OFFLINE_GRACE_MS) {
      onEnded('offline')
      return
    }
    retryTimer = setTimeout(() => void start(), HLS_RETRY_MS)
  }

  const start = async () => {
    const url = resolveTwitchSource ? await resolveTwitchSource().catch(() => null) : null
    if (destroyed) return
    if (!url) {
      // Never played → embed fallback. Lost mid-stream → keep retrying in the grace.
      if (lostSince === null) fallBackToEmbed()
      else retry()
      return
    }
    hls?.destroy()
    const handle = await mountHls(url, container, video, {
      onStartFailed: () => (lostSince === null ? fallBackToEmbed() : retry()),
      onLost: retry,
    })
    if (destroyed) handle.destroy()
    else hls = handle
  }

  void start()

  return {
    setVolume(nextVolume, nextMuted) {
      volume = nextVolume
      muted = nextMuted
      video.volume = nextVolume / 100
      video.muted = nextMuted || nextVolume === 0
      embed?.setVolume(nextVolume, nextMuted)
    },
    destroy() {
      destroyed = true
      if (retryTimer) clearTimeout(retryTimer)
      hls?.destroy()
      embed?.destroy()
      video.remove()
    },
  }
}

/** Mount the insert's player. YouTube needs its IFrame API loaded first (null
 *  when it isn't); Twitch loads what it needs itself. */
export function mountLiveInsert(options: LiveInsertMountOptions): LiveInsertController | null {
  return options.insert.source_type === 'twitch_live' ? mountTwitch(options) : mountYouTube(options)
}
