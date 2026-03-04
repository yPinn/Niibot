import { useEffect, useRef, useState } from 'react'

interface TwitchPlayerProps {
  channel: string
  width?: string | number
  height?: string | number
  muted?: boolean
  autoplay?: boolean
  className?: string
}

interface TwitchPlayerInstance {
  destroy: () => void
}

interface TwitchWindow extends Window {
  Twitch?: {
    Player: new (element: HTMLElement, options: Record<string, unknown>) => TwitchPlayerInstance
  }
}

declare const window: TwitchWindow

export default function TwitchPlayer({
  channel,
  width = '100%',
  height = '100%',
  muted = true,
  autoplay = true,
  className = '',
}: TwitchPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<TwitchPlayerInstance | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let cancelled = false

    function initPlayer() {
      if (cancelled || !containerRef.current || !window.Twitch) return

      // destroy previous instance
      if (playerRef.current) {
        try {
          playerRef.current.destroy()
        } catch {
          // ignore
        }
        playerRef.current = null
      }

      try {
        playerRef.current = new window.Twitch.Player(containerRef.current, {
          channel,
          width,
          height,
          muted,
          autoplay,
          parent: [window.location.hostname],
        })
      } catch (error) {
        if (import.meta.env.DEV) console.error('Error initializing Twitch player:', error)
      }
    }

    if (window.Twitch) {
      initPlayer()
    } else {
      const existing = document.querySelector('script[src*="embed.twitch.tv"]')
      if (!existing) {
        const script = document.createElement('script')
        script.src = 'https://player.twitch.tv/js/embed/v1.js'
        script.async = true
        document.body.appendChild(script)
      }

      const poll = setInterval(() => {
        if (window.Twitch) {
          clearInterval(poll)
          clearTimeout(timeout)
          initPlayer()
        }
      }, 100)

      // Give up after 10 seconds if the Twitch embed script never loads
      const timeout = setTimeout(() => {
        clearInterval(poll)
        if (!cancelled) setLoadError(true)
      }, 10_000)

      return () => {
        cancelled = true
        clearInterval(poll)
        clearTimeout(timeout)
      }
    }

    return () => {
      cancelled = true
      if (playerRef.current) {
        try {
          playerRef.current.destroy()
        } catch {
          // ignore
        }
        playerRef.current = null
      }
    }
  }, [channel, width, height, muted, autoplay])

  if (loadError) {
    return (
      <div
        className={`flex items-center justify-center text-muted-foreground text-sm ${className}`}
      >
        播放器載入失敗
      </div>
    )
  }

  return <div ref={containerRef} className={className} />
}
