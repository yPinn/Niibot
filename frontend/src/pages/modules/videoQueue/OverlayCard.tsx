import { useState } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { EmptyState, Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Switch,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'

import { thumbnailUrl } from './utils'

function PercentInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange?: (value: string) => void
}) {
  return (
    <div className="relative w-20">
      <Input
        aria-label={label}
        type="number"
        inputMode="numeric"
        min={0}
        max={100}
        value={value}
        onChange={event => onChange?.(event.target.value)}
        className="w-full pr-7 text-right tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-label text-muted-foreground"
      >
        %
      </span>
    </div>
  )
}

export function OverlayCard({
  url,
  current,
  volumePercent = '50',
  onVolumeChange,
  insertAudioOnly = false,
  onToggleInsertAudioOnly,
  onSaveOutput,
  outputDirty = true,
  saving = false,
  onOpenGuide,
  onRotateUrl,
  rotating = false,
}: {
  url: string
  current: VideoQueueEntry | null
  volumePercent?: string
  onVolumeChange?: (value: string) => void
  insertAudioOnly?: boolean
  onToggleInsertAudioOnly?: (value: boolean) => void
  onSaveOutput?: () => void
  /** Unsaved output changes: the save button is only prominent (and enabled) then. */
  outputDirty?: boolean
  saving?: boolean
  onOpenGuide: () => void
  onRotateUrl?: () => void
  rotating?: boolean
}) {
  // The preview loads the real overlay in an iframe. It stays a click-to-load
  // poster by default: the overlay can't autoplay muted for every platform
  // (Twitch clips especially), and the "現在播放" card already shows live status.
  const [previewOpen, setPreviewOpen] = useState(false)
  const poster = current ? thumbnailUrl(current.video_type, current.video_id) : null
  const [overlayPath, capabilityFragment] = url.split('#', 2)
  const previewUrl = url
    ? `${overlayPath}${overlayPath.includes('?') ? '&' : '?'}preview=1${capabilityFragment ? `#${capabilityFragment}` : ''}`
    : ''

  // Order: the URL (what you need to set OBS up) → output settings, each a
  // uniform "title + description | control" row → the preview.
  return (
    <Card>
      <CardHeader>
        <CardTitle>OBS 畫面</CardTitle>
        <CardAction>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="如何加入 OBS"
                onClick={onOpenGuide}
              >
                <Icon icon="fa-regular fa-circle-question" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">如何加入 OBS</TooltipContent>
          </Tooltip>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-card">
        <OverlayUrlBlock
          url={url}
          obsSource={{ name: 'Niibot Video Queue', width: 640, height: 400 }}
          onRotate={onRotateUrl}
          rotating={rotating}
        />

        <div className="flex flex-col gap-card">
          <SettingRow title="播放音量" description="影片與直播共用">
            <div className="flex shrink-0 items-center gap-element">
              <PercentInput label="播放音量" value={volumePercent} onChange={onVolumeChange} />
              {onSaveOutput && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="icon"
                      variant={outputDirty ? 'default' : 'outline'}
                      disabled={saving || !outputDirty}
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
          {onToggleInsertAudioOnly && (
            <SettingRow title="直播僅聲音" description="不顯示直播畫面">
              <Switch
                aria-label="直播僅聲音"
                checked={insertAudioOnly}
                onCheckedChange={onToggleInsertAudioOnly}
              />
            </SettingRow>
          )}
        </div>

        {/* Same 16:10 as the 640×400 overlay. Nothing to show → the same
            EmptyState as the rest of the page; dark only once there is media. */}
        <div
          className={`relative aspect-[16/10] overflow-hidden rounded-lg border ${
            previewOpen || poster ? 'bg-black' : 'bg-muted/30'
          }`}
        >
          {previewOpen ? (
            <>
              <iframe
                src={previewUrl}
                className="block h-full w-full"
                title="畫面預覽"
                allow="autoplay"
              />
              <Badge
                variant="secondary"
                className="pointer-events-none absolute top-2 left-2 bg-black/75 text-white shadow-sm"
              >
                同步預覽 · 靜音
              </Badge>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              aria-label="載入預覽"
              className="group absolute inset-0"
            >
              {poster ? (
                <span className="flex h-full flex-col items-center justify-center gap-element p-card text-center text-white/85 group-hover:text-white">
                  <img
                    src={poster}
                    alt=""
                    className="absolute inset-0 h-full w-full object-cover opacity-40 transition-opacity group-hover:opacity-55"
                  />
                  <Icon
                    icon="fa-solid fa-circle-play"
                    wrapperClassName="relative size-20 opacity-60"
                    className="text-[5rem]"
                  />
                  <span className="relative text-card-title font-medium">載入預覽</span>
                  <span className="relative text-sub text-white/60">與 OBS 同步，靜音</span>
                </span>
              ) : (
                <EmptyState
                  icon="fa-solid fa-circle-play"
                  title="載入預覽"
                  description="目前沒有播放"
                  className="h-full p-card transition-opacity group-hover:opacity-80"
                />
              )}
            </button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
