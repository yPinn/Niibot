import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type EventConfig,
  getEventConfigs,
  toggleEventConfig,
  updateEventConfig,
} from '@/api/events'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

// 每種事件類型可用的模板變數
const TEMPLATE_VARIABLES: Record<string, { var: string; desc: string }[]> = {
  follow: [{ var: '$(user)', desc: '追隨者名稱' }],
  subscribe: [
    { var: '$(user)', desc: '訂閱者名稱' },
    { var: '$(tier)', desc: '訂閱等級 (T1/T2/T3)' },
  ],
  raid: [
    { var: '$(user)', desc: 'Raider 名稱' },
    { var: '$(count)', desc: '觀眾數量' },
  ],
}

const EVENT_TYPE_COLORS: Record<string, string> = {
  follow: 'bg-blue-500/10 text-blue-500',
  subscribe: 'bg-purple-500/10 text-purple-500',
  raid: 'bg-red-500/10 text-red-500',
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  follow: '追隨',
  subscribe: '訂閱',
  raid: 'Raid',
}

const EVENT_TYPE_NAMES: Record<string, string> = {
  follow: '新追隨者',
  subscribe: '訂閱感謝',
  raid: 'Raid 歡迎',
}

export default function Events() {
  const [events, setEvents] = useState<EventConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Sheet editing state
  const [editingEvent, setEditingEvent] = useState<EventConfig | null>(null)
  const [editTemplate, setEditTemplate] = useState('')
  const [editEnabled, setEditEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const templateInputRef = useRef<HTMLInputElement>(null)

  const fetchEvents = useCallback(async () => {
    try {
      setError(null)
      const data = await getEventConfigs()
      setEvents(data)
    } catch {
      setError('無法載入事件設定')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchEvents()
  }, [fetchEvents])

  const handleToggle = async (event: EventConfig) => {
    const newEnabled = !event.enabled
    // Optimistic update
    setEvents(prev =>
      prev.map(e => (e.event_type === event.event_type ? { ...e, enabled: newEnabled } : e))
    )
    try {
      await toggleEventConfig(event.event_type, newEnabled)
    } catch {
      // Revert on failure
      setEvents(prev =>
        prev.map(e => (e.event_type === event.event_type ? { ...e, enabled: event.enabled } : e))
      )
    }
  }

  const openEditor = (event: EventConfig) => {
    setEditingEvent(event)
    setEditTemplate(event.message_template)
    setEditEnabled(event.enabled)
  }

  const handleSave = async () => {
    if (!editingEvent) return
    setSaving(true)
    try {
      const updated = await updateEventConfig(editingEvent.event_type, {
        message_template: editTemplate,
        enabled: editEnabled,
      })
      setEvents(prev => prev.map(e => (e.event_type === updated.event_type ? updated : e)))
      setEditingEvent(null)
    } catch {
      // Keep sheet open on error
    } finally {
      setSaving(false)
    }
  }

  const insertVariable = (varStr: string) => {
    const input = templateInputRef.current
    if (!input) {
      setEditTemplate(prev => prev + varStr)
      return
    }
    const start = input.selectionStart ?? editTemplate.length
    const end = input.selectionEnd ?? editTemplate.length
    const newValue = editTemplate.slice(0, start) + varStr + editTemplate.slice(end)
    setEditTemplate(newValue)
    // Restore cursor position after React re-render
    requestAnimationFrame(() => {
      input.focus()
      const newPos = start + varStr.length
      input.setSelectionRange(newPos, newPos)
    })
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-bold">Events</h1>
        <p className="text-muted-foreground">管理頻道事件和自動回應</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>事件列表</CardTitle>
          <CardDescription>設定頻道事件觸發時的自動回應訊息</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              載入中...
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-8 text-destructive">{error}</div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>事件名稱</TableHead>
                    <TableHead>類型</TableHead>
                    <TableHead>訊息模板</TableHead>
                    <TableHead className="text-right">觸發次數</TableHead>
                    <TableHead className="text-center">狀態</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.map(event => (
                    <TableRow key={event.event_type}>
                      <TableCell className="font-medium">
                        {EVENT_TYPE_NAMES[event.event_type] || event.event_type}
                      </TableCell>
                      <TableCell>
                        <Badge className={EVENT_TYPE_COLORS[event.event_type] || ''}>
                          {EVENT_TYPE_LABELS[event.event_type] || event.event_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-md truncate font-mono text-xs">
                        {event.message_template}
                      </TableCell>
                      <TableCell className="text-right">{event.trigger_count}</TableCell>
                      <TableCell className="text-center">
                        <div className="flex justify-center">
                          <Switch
                            checked={event.enabled}
                            onCheckedChange={() => handleToggle(event)}
                          />
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => openEditor(event)}>
                          編輯
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit Sheet */}
      <Sheet open={!!editingEvent} onOpenChange={open => !open && setEditingEvent(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>
              編輯{' '}
              {editingEvent
                ? EVENT_TYPE_NAMES[editingEvent.event_type] || editingEvent.event_type
                : ''}
            </SheetTitle>
            <SheetDescription>修改事件觸發時的自動回應訊息</SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-6 px-4">
            {/* Message Template */}
            <div className="flex flex-col gap-2">
              <Label>訊息模板</Label>
              <Input
                ref={templateInputRef}
                value={editTemplate}
                onChange={e => setEditTemplate(e.target.value)}
                placeholder="輸入回應訊息..."
                className="font-mono text-sm"
              />

              {/* Available Variables */}
              {editingEvent && TEMPLATE_VARIABLES[editingEvent.event_type] && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs text-muted-foreground">可用變數（點擊插入）</span>
                  <div className="flex flex-wrap gap-1.5">
                    {TEMPLATE_VARIABLES[editingEvent.event_type].map(v => (
                      <button
                        key={v.var}
                        type="button"
                        onClick={() => insertVariable(v.var)}
                        className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono hover:bg-accent transition-colors cursor-pointer"
                      >
                        <span className="text-primary">{v.var}</span>
                        <span className="text-muted-foreground">— {v.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Enabled Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <Label>啟用</Label>
                <span className="text-xs text-muted-foreground">關閉後事件觸發時不會發送訊息</span>
              </div>
              <Switch checked={editEnabled} onCheckedChange={setEditEnabled} />
            </div>
          </div>

          <SheetFooter className="flex-row justify-end gap-2">
            <SheetClose asChild>
              <Button variant="outline">取消</Button>
            </SheetClose>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? '儲存中...' : '儲存'}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </main>
  )
}
