import { useEffect, useRef } from 'react'

interface TwitchPlayerProps {
  channel: string
  width?: string | number
  height?: string | number
  muted?: boolean
  autoplay?: boolean
  className?: string
}

interface TwitchPlayer {
  destroy: () => void
}

interface TwitchWindow extends Window {
  Twitch?: {
    Player: new (element: HTMLElement, options: Record<string, unknown>) => TwitchPlayer
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
  const playerRef = useRef<HTMLDivElement>(null)
  const twitchPlayerRef = useRef<TwitchPlayer | null>(null)
  const scriptLoadedRef = useRef<boolean>(false)

  useEffect(() => {
    if (window.Twitch && !scriptLoadedRef.current) {
      scriptLoadedRef.current = true
      initPlayer()
      return
    }

    const existingScript = document.querySelector('script[src*="embed.twitch.tv"]')
    if (existingScript) {
      scriptLoadedRef.current = true
      const checkTwitch = setInterval(() => {
        if (window.Twitch) {
          clearInterval(checkTwitch)
          initPlayer()
        }
      }, 100)
      return () => clearInterval(checkTwitch)
    }

    const script = document.createElement('script')
    script.src = 'https://player.twitch.tv/js/embed/v1.js'
    script.async = true
    script.onload = () => {
      scriptLoadedRef.current = true
      initPlayer()
    }
    document.body.appendChild(script)

    function initPlayer() {
      if (playerRef.current && window.Twitch) {
        try {
          twitchPlayerRef.current = new window.Twitch.Player(playerRef.current, {
            channel,
            width,
            height,
            muted,
            autoplay,
            parent: [window.location.hostname],
            allowfullscreen: true,
          })
        } catch (error) {
          console.error('Error initializing Twitch player:', error)
        }
      }
    }

    return () => {
      if (twitchPlayerRef.current) {
        try {
          twitchPlayerRef.current.destroy()
          twitchPlayerRef.current = null
        } catch {
          // Ignore cleanup errors
        }
      }
    }
  }, [channel, width, height, muted, autoplay])

  return <div ref={playerRef} className={className} />
}
