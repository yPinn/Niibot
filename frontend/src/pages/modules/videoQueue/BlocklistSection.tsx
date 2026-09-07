import { useCallback, useEffect, useImperativeHandle, useState } from 'react'
import { toast } from 'sonner'

import {
  addVideoQueueBlock,
  type BlocklistEntry,
  type BlocklistKind,
  getVideoQueueBlocklist,
  removeVideoQueueBlock,
} from '@/api/videoQueue'
import { Icon, Spinner } from '@/components/primitives'
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

// 'creator' is defined but not offered until the creator-id plumbing lands.
const ADDABLE_KINDS: BlocklistKind[] = ['video', 'keyword', 'user']

const KIND_PLACEHOLDER: Record<BlocklistKind, string> = {
  video: '影片 ID 或連結',
  creator: '創作者 ID',
  keyword: '標題關鍵字',
  user: 'Twitch 使用者名稱',
}

// Accept a full URL for the `video` kind — pull the last path/query id out of it.
function normalizeValue(kind: BlocklistKind, raw: string): string {
  const v = raw.trim()
  if (kind !== 'video') return v
  const yt = v.match(/(?:v=|youtu\.be\/|shorts\/)([A-Za-z0-9_-]{11})/)
  if (yt) return yt[1]
  const bili = v.match(/(BV[A-Za-z0-9]{10})/)
  if (bili) return bili[1]
  const clip = v.match(/(?:clips\.twitch\.tv\/|\/clip\/)([A-Za-z0-9_-]+)/)
  if (clip) return clip[1]
  return v
}

export interface BlocklistSectionHandle {
  addBlock: (kind: BlocklistKind, value: string, label?: string | null) => Promise<void>
}

export function BlocklistSection({ ref }: { ref?: React.Ref<BlocklistSectionHandle> }) {
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

  const addBlock = useCallback(async (k: BlocklistKind, v: string, label?: string | null) => {
    const normalized = normalizeValue(k, v)
    if (!normalized) return
    const created = await addVideoQueueBlock(k, normalized, label)
    setEntries(prev => [created, ...prev.filter(e => e.id !== created.id)])
  }, [])

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
    <div className="flex flex-col gap-3">
      <div>
        <p className="text-sub text-muted-foreground">封鎖清單</p>
        <p className="text-label text-muted-foreground">
          符合的影片、標題關鍵字或點播者會被所有點播管道拒絕
        </p>
      </div>

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
          className="w-56 max-w-full"
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
        <Spinner />
      ) : entries.length === 0 ? (
        <p className="text-label text-muted-foreground">目前沒有封鎖項目</p>
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
