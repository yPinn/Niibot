import { makeMountDiv } from './shared'
import type { MountContext, PlayerStrategy } from './types'

// Twitch VODs (twitch.tv/videos/{id}) play through Twitch's official embed
// player JS API — which, unlike clips, accepts a `video` param. That gives a
// real player object: `autoplay` + `.play()` are imperative (so OBS's relaxed
// autoplay policy honours them, like YouTube), `controls: false` hides the
// chrome, and the ENDED event plus a currentTime check bound the play window
// (a VOD is hours long — the backend caps duration_seconds; start_seconds is
// the `?t=` seek offset).

let _twitchReadyPromise: Promise<void> | null = null

export function loadTwitchEmbedAPI(): Promise<void> {
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

function mount(ctx: MountContext): (() => void) | void {
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
  const windowSeconds = current.duration_seconds || 600
  const alreadyPlayed = Math.max(0, joinElapsed)
  if (alreadyPlayed >= windowSeconds - 0.5) {
    handleVideoEnd(currentId)
    return
  }

  const player = new Player(makeMountDiv(containerRef.current), {
    video: current.video_id,
    parent: [window.location.hostname],
    width: '100%',
    height: '100%',
    autoplay: true,
    muted,
    time: `${Math.floor(start + alreadyPlayed)}s`,
    controls: false,
  })

  const finish = () => handleVideoEnd(currentId)
  const blocked = () => handleVideoEnd(currentId, 'autoplay_blocked')
  const applyPlaybackSettings = () => {
    player.setVolume(volumePercent / 100)
    player.setMuted(muted || volumePercent === 0)
  }
  applyPlaybackSettings()
  if (Player.READY) player.addEventListener(Player.READY, applyPlaybackSettings)
  player.addEventListener(Player.ENDED, finish)
  player.addEventListener(Player.PLAYING, () => notifyPlaybackStarted('confirmed'))
  if (Player.PLAYBACK_BLOCKED) player.addEventListener(Player.PLAYBACK_BLOCKED, blocked)
  // Belt-and-braces autoplay nudge (harmless if already playing).
  const playTimer = setTimeout(() => {
    try {
      player.play()
    } catch {
      /* ignore */
    }
  }, 500)

  setElapsed(alreadyPlayed)
  progressRef.current = setInterval(() => {
    let played: number
    try {
      played = player.getCurrentTime() - start
    } catch {
      return
    }
    setElapsed(played)
    if (played >= windowSeconds) finish()
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

export const twitchVodStrategy: PlayerStrategy = { requiresApi: 'twitch', mount }
