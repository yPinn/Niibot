import { reportClientError } from '@/lib/clientErrorReporter'

import { createStallWatch, makeMountDiv } from './shared'
import type { MountContext, PlayerStrategy } from './types'

// Twitch VODs (twitch.tv/videos/{id}) play through Twitch's embed player.
//
// hls.js is not an option for VODs: their playlists and segments live on
// Twitch's CloudFront VOD hosts, which send no CORS headers at all (checked
// 2026-10-07; the live hosts do), so a browser can't read them. Relaying the
// video through Niibot would cost per-tenant bandwidth — ruled out.
//
// The embed won't autoplay *with sound* in an OBS Browser Source, so it starts
// muted (muted autoplay is the case browsers allow) and unmutes once PLAYING
// fires. If unmuting gets it paused or blocked, it goes back to muted playback
// — a silent video beats a stuck queue — and reports it, so OBS behaviour can
// be confirmed from admin → Monitor → Errors.

let _twitchReadyPromise: Promise<void> | null = null

export function loadTwitchEmbedAPI(): Promise<void> {
  // Already available (loaded by another mount, or present before any load):
  // never wait on a cached promise from an earlier, still-pending attempt.
  if (typeof window !== 'undefined' && window.Twitch?.Player) return Promise.resolve()
  if (_twitchReadyPromise) return _twitchReadyPromise
  _twitchReadyPromise = new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.Twitch?.Player) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://player.twitch.tv/js/embed/v1.js'
    script.async = true
    script.onload = () => {
      if (window.Twitch?.Player) {
        resolve()
        return
      }
      let tries = 0
      const poll = setInterval(() => {
        if (window.Twitch?.Player) {
          clearInterval(poll)
          resolve()
        } else if (++tries > 50) {
          clearInterval(poll)
          _twitchReadyPromise = null
          reject(new Error('Twitch embed API loaded but Twitch.Player never appeared'))
        }
      }, 100)
    }
    script.onerror = () => {
      _twitchReadyPromise = null // allow retry on next mount
      reject(new Error('Failed to load Twitch embed API'))
    }
    document.head.appendChild(script)
  })
  return _twitchReadyPromise
}

/** How long after unmuting a pause still counts as "unmuting was refused". */
const UNMUTE_GRACE_MS = 3000

function mountEmbed(ctx: MountContext): (() => void) | void {
  const {
    current,
    currentId,
    joinElapsed,
    muted,
    volumePercent,
    containerRef,
    progressRef,
    setElapsed,
    notifyPlaybackStarted,
  } = ctx
  const handleVideoEnd = ctx.handleVideoEnd

  const Player = window.Twitch?.Player
  if (!Player || !containerRef.current) return

  const start = current.start_seconds || 0
  // Unknown length (Helix failed, no length limit): play until the VOD ends.
  const windowSeconds = current.duration_seconds || Number.POSITIVE_INFINITY
  const alreadyPlayed = Math.max(0, joinElapsed)
  if (alreadyPlayed >= windowSeconds - 0.5) {
    handleVideoEnd(currentId)
    return
  }

  const wantsSound = !muted && volumePercent > 0
  const player = new Player(makeMountDiv(containerRef.current), {
    video: current.video_id,
    parent: [window.location.hostname],
    width: '100%',
    height: '100%',
    autoplay: true,
    muted: true, // muted autoplay first; sound comes after PLAYING
    time: `${Math.floor(start + alreadyPlayed)}s`,
    controls: false,
  })

  let playing = false
  let unmutedAt: number | null = null
  let soundRefused = false
  const finish = () => handleVideoEnd(currentId)
  const refuseSound = () => {
    soundRefused = true
    unmutedAt = null
    try {
      player.setMuted(true)
      player.play()
    } catch {
      /* ignore */
    }
    reportClientError({
      kind: 'error',
      message: 'twitch_vod embed: unmuting after muted autoplay was refused',
      errorCode: 'VIDEO_QUEUE.TWITCH_VOD_UNMUTE_REFUSED',
    })
  }

  player.setVolume(volumePercent / 100)
  player.setMuted(true)
  player.addEventListener(Player.ENDED, finish)
  player.addEventListener(Player.PLAYING, () => {
    if (playing) return
    playing = true
    notifyPlaybackStarted('confirmed')
    if (wantsSound && !soundRefused) {
      unmutedAt = Date.now()
      player.setVolume(volumePercent / 100)
      player.setMuted(false)
    }
  })
  player.addEventListener(Player.PAUSE, () => {
    if (unmutedAt !== null && Date.now() - unmutedAt < UNMUTE_GRACE_MS) refuseSound()
  })
  if (Player.PLAYBACK_BLOCKED) {
    player.addEventListener(Player.PLAYBACK_BLOCKED, () => {
      if (unmutedAt !== null) refuseSound()
      else handleVideoEnd(currentId, 'autoplay_blocked')
    })
  }
  // Belt-and-braces autoplay nudge (harmless if already playing).
  const playTimer = setTimeout(() => {
    try {
      player.play()
    } catch {
      /* ignore */
    }
  }, 500)

  // Armed by the first PLAYING (`playing`); the startup watchdog covers before that.
  const stallWatch = createStallWatch('twitch_vod', {
    recover: () => {
      try {
        player.seek(player.getCurrentTime())
        player.play()
      } catch {
        /* ignore */
      }
    },
    giveUp: () => {
      clearInterval(progressRef.current ?? undefined)
      progressRef.current = null
      handleVideoEnd(currentId, 'provider_error')
    },
  })

  setElapsed(alreadyPlayed)
  progressRef.current = setInterval(() => {
    let played: number
    try {
      played = player.getCurrentTime() - start
    } catch {
      return
    }
    let loaded = ''
    try {
      loaded = player.getVideo().replace(/^v/, '')
    } catch {
      /* older embed without getVideo — the window check below still applies */
    }
    // A VOD's length is fixed when the player loads it (an in-progress VOD
    // included); once that end is reached Twitch autoplays an unrelated VOD.
    // If ENDED was missed, played time would restart near 0 and never reach
    // the window — stop as soon as a different video is loaded instead.
    if (loaded && loaded !== current.video_id) {
      finish()
      return
    }
    setElapsed(played)
    if (played >= windowSeconds) {
      finish()
      return
    }
    if (playing) stallWatch(played)
  }, 1000)

  return () => {
    clearTimeout(playTimer)
    try {
      player.destroy()
    } catch {
      /* ignore */
    }
  }
}

function mount(ctx: MountContext): () => void {
  let disposed = false
  let cleanup: (() => void) | void
  loadTwitchEmbedAPI()
    .then(() => {
      if (!disposed) cleanup = mountEmbed(ctx)
    })
    .catch(() => ctx.handleVideoEnd(ctx.currentId, 'provider_error'))
  return () => {
    disposed = true
    if (typeof cleanup === 'function') cleanup()
  }
}

// The embed script loads inside mount(), so no external API gates it here.
export const twitchVodStrategy: PlayerStrategy = { requiresApi: null, mount }
