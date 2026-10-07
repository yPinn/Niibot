import type { VideoQueueLiveInsert } from '@/api/videoQueue'

import { makeMountDiv } from './shared'
import type { TwitchPlayerInstance, YTPlayer } from './types'

// Live insert (直播插播): the broadcaster plays someone's ongoing live stream
// open-ended — background music, a watch-along — instead of the queue. Unlike
// a queue entry there is no duration, no countdown and no advance: it plays
// until the broadcaster stops it (the row disappears from the stream) or the
// stream itself ends, which the player reports here exactly once.
//
// Ending is detected from player events only — never by polling our API or
// Helix (see the Cloudflare request budget in docs/guides/cloudflare-pages.md).

/** Twitch fires OFFLINE on a brief broadcaster disconnect too; only end once it
 *  has stayed offline this long (an ONLINE in between cancels). */
export const OFFLINE_GRACE_MS = 60_000

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
}

function mountTwitch({
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

/** Mount the insert's player; null when its embed API isn't loaded yet. */
export function mountLiveInsert(options: LiveInsertMountOptions): LiveInsertController | null {
  return options.insert.source_type === 'twitch_live' ? mountTwitch(options) : mountYouTube(options)
}
