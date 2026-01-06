import { useEffect, useRef } from 'react'

interface TwitchPlayerProps {
  channel: string
  width?: string | number
  height?: string | number
  muted?: boolean
  autoplay?: boolean
  className?: string
}

export default function TwitchPlayer({
  channel,
  width = '100%',
  height = '100%',
  muted = true,
  autoplay = true,
  className = '',
}: TwitchPlayerProps) {
  const playerRef = useRef<HTMLDivElement>(null)
  const twitchPlayerRef = useRef<any>(null)
  const scriptLoadedRef = useRef<boolean>(false)

  useEffect(() => {
    // 檢查是否已載入 Twitch SDK
    if ((window as any).Twitch && !scriptLoadedRef.current) {
      scriptLoadedRef.current = true
      initPlayer()
      return
    }

    // 檢查是否已存在 script 標籤
    const existingScript = document.querySelector('script[src*="embed.twitch.tv"]')
    if (existingScript) {
      scriptLoadedRef.current = true
      // 等待 SDK 載入完成
      const checkTwitch = setInterval(() => {
        if ((window as any).Twitch) {
          clearInterval(checkTwitch)
          initPlayer()
        }
      }, 100)
      return () => clearInterval(checkTwitch)
    }

    // 載入 Twitch Embed Script
    const script = document.createElement('script')
    script.src = 'https://player.twitch.tv/js/embed/v1.js'
    script.async = true
    script.onload = () => {
      scriptLoadedRef.current = true
      initPlayer()
    }
    document.body.appendChild(script)

    function initPlayer() {
      if (playerRef.current && (window as any).Twitch) {
        // 創建 Twitch Player
        try {
          twitchPlayerRef.current = new (window as any).Twitch.Player(playerRef.current, {
            channel,
            width,
            height,
            muted,
            autoplay,
            // 根據官方文檔，只包含 video 播放器
            parent: [window.location.hostname],
            allowfullscreen: true,
          })
        } catch (error) {
          console.error('Error initializing Twitch player:', error)
        }
      }
    }

    return () => {
      // 清理播放器實例
      if (twitchPlayerRef.current) {
        try {
          twitchPlayerRef.current.destroy()
          twitchPlayerRef.current = null
        } catch (error) {
          // 靜默處理清理錯誤
        }
      }
    }
  }, [channel, width, height, muted, autoplay])

  return <div ref={playerRef} className={className} />
}
