import { useState } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { Icon } from '@/components/primitives'
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui'

import { thumbnailUrl } from './utils'

export function OverlayCard({
  url,
  current,
  onOpenGuide,
}: {
  url: string
  current: VideoQueueEntry | null
  onOpenGuide: () => void
}) {
  // The preview loads the real overlay in an iframe. It stays a click-to-load
  // poster by default: the overlay can't autoplay muted for every platform
  // (Twitch clips especially), and the "現在播放" card already shows live status.
  const [previewOpen, setPreviewOpen] = useState(false)
  const poster = current ? thumbnailUrl(current.video_type, current.video_id) : null

  return (
    <Card className="lg:h-full">
      <CardHeader>
        <CardTitle>OBS 畫面</CardTitle>
        <CardDescription>加到 OBS 後，觀眾點播的影片會自動出現在直播畫面上</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-card">
        <OverlayUrlBlock url={url} />

        <div className="relative aspect-video overflow-hidden rounded-lg border bg-black lg:aspect-auto lg:min-h-0 lg:flex-1">
          {previewOpen ? (
            <iframe
              src={`${url}?preview=1`}
              className="block h-full w-full"
              title="Overlay 預覽"
              allow="autoplay"
            />
          ) : (
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              className="group absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/80 hover:text-white"
            >
              {poster && (
                <img
                  src={poster}
                  alt=""
                  className="absolute inset-0 h-full w-full object-cover opacity-40 transition-opacity group-hover:opacity-55"
                />
              )}
              <Icon
                icon="fa-solid fa-circle-play"
                wrapperClassName="relative size-9"
                className="size-9"
              />
              <span className="relative text-sub">{current ? '載入預覽（靜音）' : '載入預覽'}</span>
            </button>
          )}
        </div>

        <Button variant="outline" size="sm" className="self-start" onClick={onOpenGuide}>
          <Icon icon="fa-regular fa-circle-question" wrapperClassName="mr-1.5 size-3.5" />
          如何加入 OBS
        </Button>
      </CardContent>
    </Card>
  )
}
