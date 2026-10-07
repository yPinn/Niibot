import { type FormEvent, useState } from 'react'

import type { VideoQueueLiveInsert } from '@/api/videoQueue'
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
  Switch,
} from '@/components/ui'

function liveWatchUrl(insert: Pick<VideoQueueLiveInsert, 'source_type' | 'source_id'>) {
  return insert.source_type === 'twitch_live'
    ? `https://www.twitch.tv/${insert.source_id}`
    : `https://youtu.be/${insert.source_id}`
}

/**
 * Live insert (直播插播): the broadcaster plays an ongoing live stream
 * open-ended in the overlay — background music, a watch-along — while the
 * queue waits. Not a queue entry: no length, no review, stops only when the
 * broadcaster ends it or the stream does.
 */
export function InsertCard({
  insert,
  volumePercent,
  audioOnly,
  onStart,
  onStop,
  onSaveDefaults,
}: {
  insert: VideoQueueLiveInsert | null
  volumePercent: number
  audioOnly: boolean
  onStart: (url: string) => Promise<void>
  onStop: () => Promise<void>
  onSaveDefaults: (patch: {
    insert_volume_percent?: number
    insert_audio_only?: boolean
  }) => Promise<void>
}) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  // null = not being edited: show the saved value (which can change elsewhere).
  const [volumeDraft, setVolumeDraft] = useState<string | null>(null)
  const shownVolume = volumeDraft ?? String(volumePercent)

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    try {
      await action()
    } catch {
      // the caller already toasted the error
    } finally {
      setBusy(false)
    }
  }

  const handleStart = (event: FormEvent) => {
    event.preventDefault()
    const value = url.trim()
    if (!value) return
    void run(async () => {
      await onStart(value)
      setUrl('')
    })
  }

  const volume = parseInt(shownVolume, 10)
  const volumeValid = !isNaN(volume) && volume >= 0 && volume <= 100

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          直播插播
          {insert && (
            <Badge variant="outline" className="text-label border-status-live/60 text-status-live">
              LIVE
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          播放進行中的直播當背景音樂或一起看，期間佇列暫停；直播結束或手動結束後恢復
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-card">
        {insert ? (
          <div className="flex items-center gap-card min-w-0">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="shrink-0 text-label text-muted-foreground">
                  {insert.source_type === 'twitch_live' ? 'Twitch' : 'YouTube'}
                </span>
                <span className="truncate font-medium">
                  {insert.creator_name || insert.source_id}
                </span>
              </div>
              {insert.title && (
                <span className="truncate text-sub text-muted-foreground" title={insert.title}>
                  {insert.title}
                </span>
              )}
            </div>
            <Button size="icon-sm" variant="ghost" asChild title="在新分頁開啟直播">
              <a href={liveWatchUrl(insert)} target="_blank" rel="noreferrer">
                <Icon icon="fa-solid fa-arrow-up-right-from-square" className="size-3" />
                <span className="sr-only">在新分頁開啟直播</span>
              </a>
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(onStop)}>
              {busy ? (
                <Spinner className="mr-1.5" />
              ) : (
                <Icon icon="fa-solid fa-stop" className="mr-1.5 size-3" />
              )}
              結束插播
            </Button>
          </div>
        ) : (
          <form className="flex gap-2" onSubmit={handleStart}>
            <Input
              aria-label="直播網址"
              placeholder="Twitch 頻道或 YouTube 直播網址"
              value={url}
              onChange={event => setUrl(event.target.value)}
            />
            <Button type="submit" size="sm" className="h-9 shrink-0" disabled={busy || !url.trim()}>
              {busy ? (
                <Spinner className="mr-1.5" />
              ) : (
                <Icon icon="fa-solid fa-tower-broadcast" className="mr-1.5 size-3" />
              )}
              開始插播
            </Button>
          </form>
        )}

        <SettingRow
          title="插播音量"
          description="背景音樂通常要比點播小聲；調整後立即套用到正在插播的直播"
          className="flex-col items-stretch sm:flex-row sm:items-center"
        >
          <div className="flex w-full items-center justify-end gap-2 sm:w-auto sm:shrink-0">
            <div className="relative w-20 shrink-0">
              <Input
                aria-label="插播音量"
                type="number"
                inputMode="numeric"
                min={0}
                max={100}
                value={shownVolume}
                onChange={event => setVolumeDraft(event.target.value)}
                className="w-full pr-7 text-right tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
              <span
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-label text-muted-foreground"
              >
                %
              </span>
            </div>
            <Button
              size="icon"
              aria-label="儲存插播音量"
              disabled={busy || !volumeValid || volume === volumePercent}
              onClick={() =>
                void run(async () => {
                  await onSaveDefaults({ insert_volume_percent: volume })
                  setVolumeDraft(null)
                })
              }
            >
              <Icon icon="fa-solid fa-floppy-disk" />
            </Button>
          </div>
        </SettingRow>

        <SettingRow title="僅聲音" description="OBS 畫面不顯示直播，只播放聲音">
          <Switch
            aria-label="僅聲音"
            checked={audioOnly}
            disabled={busy}
            onCheckedChange={value => void run(() => onSaveDefaults({ insert_audio_only: value }))}
          />
        </SettingRow>
      </CardContent>
    </Card>
  )
}
