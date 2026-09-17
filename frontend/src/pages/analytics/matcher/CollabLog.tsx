import { useCallback, useEffect, useState } from 'react'

import {
  type CollabConversion,
  createCollabEvent,
  deleteCollabEvent,
  listCollabEvents,
} from '@/api/analytics'
import { Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
  Textarea,
} from '@/components/ui'
import { formatDateTimeShort } from '@/lib/format'

interface CollabLogProps {
  partnerChannelId: string
  windowDays: number
}

export function CollabLog({ partnerChannelId, windowDays }: CollabLogProps) {
  const [collabs, setCollabs] = useState<CollabConversion[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const fetchCollabs = useCallback(async () => {
    setLoading(true)
    try {
      setCollabs(await listCollabEvents(partnerChannelId))
    } catch {
      setCollabs([])
    } finally {
      setLoading(false)
    }
  }, [partnerChannelId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchCollabs()
  }, [fetchCollabs])

  const handleCreate = async () => {
    setSubmitting(true)
    try {
      await createCollabEvent(partnerChannelId, windowDays, note.trim() || null)
      setNote('')
      setDialogOpen(false)
      await fetchCollabs()
    } catch {
      // silent — dialog stays open so the user can retry
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    setCollabs(prev => prev.filter(c => c.id !== id))
    try {
      await deleteCollabEvent(partnerChannelId, id)
    } catch {
      await fetchCollabs()
    }
  }

  return (
    <div className="flex flex-col gap-2 shrink-0">
      <div className="flex items-center justify-between">
        <span className="text-label text-muted-foreground">合作紀錄</span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 px-2 text-label"
          onClick={() => setDialogOpen(true)}
        >
          <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1 size-3" />
          標記本次合作
        </Button>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>標記本次合作</DialogTitle>
              <DialogDescription>
                會把目前「{windowDays} 天」窗口下、只在對方頻道出現過的觀眾記錄下來，之後 14
                天內追蹤、訂閱或回來聊天都算這次合作帶來的轉換。
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-element">
              <Label htmlFor="collab-note">備註（選填）</Label>
              <Textarea
                id="collab-note"
                value={note}
                onChange={event => setNote(event.target.value)}
                placeholder="例如：互相 raid、聯動企劃"
                disabled={submitting}
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={submitting}>
                取消
              </Button>
              <Button onClick={() => void handleCreate()} disabled={submitting}>
                {submitting && <Spinner className="mr-1.5 size-3" />}
                確認標記
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-4">
          <Spinner className="size-4" />
        </div>
      ) : collabs.length === 0 ? (
        <p className="text-label text-muted-foreground">尚無合作紀錄</p>
      ) : (
        <div className="scrollbar flex max-h-48 flex-col gap-1.5 overflow-y-auto">
          {collabs.map(collab => (
            <div
              key={collab.id}
              className="flex items-center justify-between gap-2 rounded-md border bg-muted/20 px-2.5 py-1.5"
            >
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-label font-medium">
                  {formatDateTimeShort(collab.occurred_at)}
                  {collab.note && (
                    <span className="text-muted-foreground font-normal"> · {collab.note}</span>
                  )}
                </span>
                <div className="flex items-center gap-1 flex-wrap">
                  <Badge variant="secondary" className="text-label py-0">
                    {collab.target_count} 目標
                  </Badge>
                  <Badge variant="secondary" className="text-label py-0">
                    {collab.followed_count} 追蹤
                  </Badge>
                  <Badge variant="secondary" className="text-label py-0">
                    {collab.subscribed_count} 訂閱
                  </Badge>
                  <Badge variant="secondary" className="text-label py-0">
                    {collab.returned_count} 回訪
                  </Badge>
                  <Badge variant="outline" className="text-label py-0 font-semibold">
                    {collab.converted_pct}% 轉換
                  </Badge>
                </div>
              </div>
              <button
                type="button"
                onClick={() => void handleDelete(collab.id)}
                className="text-muted-foreground/50 hover:text-destructive transition-colors shrink-0"
              >
                <Icon icon="fa-solid fa-trash" className="text-label" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
