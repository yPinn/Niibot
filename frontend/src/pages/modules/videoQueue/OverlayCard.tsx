import { useState } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'

import { thumbnailUrl } from './utils'

export function OverlayCard({
  url,
  current,
  volumePercent = '100',
  onVolumeChange,
  onSaveOutput,
  saving = false,
  onOpenGuide,
  onRotateUrl,
  rotating = false,
}: {
  url: string
  current: VideoQueueEntry | null
  volumePercent?: string
  onVolumeChange?: (value: string) => void
  onSaveOutput?: () => void
  saving?: boolean
  onOpenGuide: () => void
  onRotateUrl?: () => void
  rotating?: boolean
}) {
  // The preview loads the real overlay in an iframe. It stays a click-to-load
  // poster by default: the overlay can't autoplay muted for every platform
  // (Twitch clips especially), and the "現在播放" card already shows live status.
  const [previewOpen, setPreviewOpen] = useState(false)
  const [confirmRotate, setConfirmRotate] = useState(false)
  const poster = current ? thumbnailUrl(current.video_type, current.video_id) : null
  const [overlayPath, capabilityFragment] = url.split('#', 2)
  const previewUrl = url
    ? `${overlayPath}${overlayPath.includes('?') ? '&' : '?'}preview=1${capabilityFragment ? `#${capabilityFragment}` : ''}`
    : ''

  return (
    <Card className="lg:h-full">
      <CardHeader>
        <CardTitle>OBS 畫面</CardTitle>
        <CardDescription>加到 OBS 後，觀眾點播的影片會自動出現在直播畫面上</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-card">
        <SettingRow
          title="播放器音量"
          description="YouTube、Twitch VOD 與直接播放影片可調；嵌入式備援播放器僅支援靜音"
          className="flex-col items-stretch sm:flex-row sm:items-center"
        >
          <div className="flex w-full items-center justify-end gap-2 sm:w-auto sm:shrink-0">
            <div className="relative w-20 shrink-0">
              <Input
                aria-label="播放器音量"
                type="number"
                inputMode="numeric"
                min={0}
                max={100}
                value={volumePercent}
                onChange={event => onVolumeChange?.(event.target.value)}
                className="w-full pr-7 text-right tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
              <span
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-label text-muted-foreground"
              >
                %
              </span>
            </div>
            {onSaveOutput && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    disabled={saving}
                    onClick={onSaveOutput}
                    aria-label="儲存播放設定"
                  >
                    {saving ? <Spinner /> : <Icon icon="fa-solid fa-floppy-disk" />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">儲存播放設定</TooltipContent>
              </Tooltip>
            )}
          </div>
        </SettingRow>

        <OverlayUrlBlock url={url} />

        <div className="relative aspect-video overflow-hidden rounded-lg border bg-black lg:aspect-auto lg:min-h-0 lg:flex-1">
          {previewOpen ? (
            <>
              <iframe
                src={previewUrl}
                className="block h-full w-full"
                title="Overlay 預覽"
                allow="autoplay"
              />
              <Badge
                variant="secondary"
                className="pointer-events-none absolute top-2 left-2 bg-black/75 text-white shadow-sm"
              >
                跟隨正式 Overlay · 靜音 · 唯讀
              </Badge>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              aria-label="載入同步預覽"
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
              <span className="relative text-sub">載入同步預覽</span>
              <span className="relative text-label text-white/55">
                {current
                  ? '跟隨目前項目；嵌入備援可能從頭開始'
                  : '等待正式 Overlay 播放，靜音且唯讀'}
              </span>
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onOpenGuide}>
            <Icon icon="fa-regular fa-circle-question" wrapperClassName="mr-1.5 size-3.5" />
            如何加入 OBS
          </Button>
          {onRotateUrl && (
            <Button
              variant="ghost"
              size="sm"
              disabled={rotating}
              onClick={() => setConfirmRotate(true)}
            >
              <Icon icon="fa-solid fa-rotate" wrapperClassName="mr-1.5 size-3.5" />
              重設 OBS 網址
            </Button>
          )}
        </div>
      </CardContent>
      <DeleteConfirmDialog
        open={confirmRotate}
        onOpenChange={setConfirmRotate}
        title="重設 OBS 網址？"
        description="目前的網址會立即失效；請把新網址重新貼到 OBS Browser Source。"
        actionLabel="重設網址"
        onConfirm={() => {
          setConfirmRotate(false)
          onRotateUrl?.()
        }}
      />
    </Card>
  )
}
