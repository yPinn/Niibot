import { useCallback, useEffect, useImperativeHandle, useState } from 'react'
import { toast } from 'sonner'

import {
  addVideoQueueBlock,
  type BlocklistEntry,
  type BlocklistKind,
  getVideoQueueBlocklist,
  removeVideoQueueBlock,
  type VideoType,
} from '@/api/videoQueue'
import { EmptyState, Icon, Spinner } from '@/components/primitives'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Badge,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

const KIND_LABEL: Record<BlocklistKind, string> = {
  video: '影片',
  creator: '創作者',
  keyword: '關鍵字',
  user: '點播者',
}

const ADDABLE_KINDS: BlocklistKind[] = ['video', 'creator', 'keyword', 'user']

const PROVIDER_LABEL: Record<VideoType, string> = {
  youtube: 'YouTube',
  twitch_clip: 'Twitch Clip',
  twitch_vod: 'Twitch VOD',
  bilibili: 'Bilibili',
  instagram_reel: 'Instagram',
}

const KIND_PLACEHOLDER: Record<BlocklistKind, string> = {
  video: '影片 ID 或連結',
  creator: '創作者 ID（YouTube 頻道 ID／Bilibili UID／Twitch 頻道名／IG 帳號）',
  keyword: '標題關鍵字',
  user: 'Twitch 使用者名稱',
}

export interface BlocklistSectionHandle {
  addBlock: (
    kind: BlocklistKind,
    value: string,
    label?: string | null,
    videoType?: VideoType | null
  ) => Promise<void>
}

export function BlocklistSection({
  ref,
  hideHeader = false,
}: {
  ref?: React.Ref<BlocklistSectionHandle>
  /** Omit the built-in title/description when a parent Card already supplies them. */
  hideHeader?: boolean
}) {
  const [entries, setEntries] = useState<BlocklistEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [kind, setKind] = useState<BlocklistKind>('keyword')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setEntries(await getVideoQueueBlocklist())
    } catch (e) {
      toastApiError(e, '載入封鎖清單失敗')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  const addBlock = useCallback(
    async (k: BlocklistKind, v: string, label?: string | null, videoType?: VideoType | null) => {
      const trimmed = v.trim()
      if (!trimmed) return
      // A pasted video URL (kind === 'video') is normalized server-side —
      // it resolves b23.tv/share redirects, av→BV, etc., and never logs the
      // raw link (may carry tracking params). A caller that already knows
      // the native id + platform (e.g. the history "封鎖" button) still
      // passes videoType explicitly and skips that resolution.
      const created =
        videoType === undefined
          ? await addVideoQueueBlock(k, trimmed, label)
          : await addVideoQueueBlock(k, trimmed, label, videoType)
      setEntries(prev => [created, ...prev.filter(e => e.id !== created.id)])
    },
    []
  )

  // Let the parent (history "封鎖" button) push a block through this component.
  useImperativeHandle(ref, () => ({ addBlock }), [addBlock])

  const handleAdd = async () => {
    if (!value.trim() || busy) return
    setBusy(true)
    try {
      await addBlock(kind, value)
      setValue('')
      toast.success('已加入封鎖清單')
    } catch (e) {
      toastApiError(e, '加入封鎖清單失敗')
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (id: number) => {
    const prev = entries
    setEntries(entries.filter(e => e.id !== id))
    try {
      await removeVideoQueueBlock(id)
    } catch (e) {
      setEntries(prev)
      toastApiError(e, '移除封鎖項目失敗')
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-card">
      {!hideHeader && (
        <div>
          <p className="text-sub text-muted-foreground">封鎖清單</p>
          <p className="text-label text-muted-foreground">
            符合的影片、標題關鍵字或點播者會被所有點播管道拒絕
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Select value={kind} onValueChange={v => setKind(v as BlocklistKind)}>
          <SelectTrigger className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ADDABLE_KINDS.map(k => (
              <SelectItem key={k} value={k}>
                {KIND_LABEL[k]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAdd()}
          placeholder={KIND_PLACEHOLDER[kind]}
          className="min-w-36 flex-1"
        />
        <Button size="sm" variant="outline" onClick={handleAdd} disabled={busy || !value.trim()}>
          {busy ? (
            <Spinner className="mr-1.5" />
          ) : (
            <Icon icon="fa-solid fa-ban" className="mr-1.5" />
          )}
          封鎖
        </Button>
      </div>

      {loading ? (
        <TableSkeletonRows count={3} />
      ) : entries.length === 0 ? (
        <EmptyState
          className="min-h-48"
          icon="fa-solid fa-ban"
          title="尚無封鎖項目"
          description="新增後會顯示在這裡"
        />
      ) : (
        <ul className="flex flex-col gap-1">
          {entries.map(entry => (
            <li
              key={entry.id}
              className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1"
            >
              <Badge variant="outline" className="shrink-0 text-label">
                {KIND_LABEL[entry.kind]}
              </Badge>
              {entry.video_type && (
                <Badge variant="secondary" className="shrink-0 text-label">
                  {PROVIDER_LABEL[entry.video_type]}
                </Badge>
              )}
              <span className="min-w-0 flex-1 truncate text-sub" title={entry.label || entry.value}>
                {entry.label || entry.value}
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="移除"
                onClick={() => handleRemove(entry.id)}
              >
                <Icon icon="fa-solid fa-xmark" className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
