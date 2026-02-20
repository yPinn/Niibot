import { useCallback, useEffect, useRef, useState } from 'react'

import {
  createTimer,
  deleteTimer,
  getTimerConfigs,
  type TimerConfig,
  type TimerCreate,
  type TimerUpdate,
  toggleTimer,
  updateTimer,
} from '@/api/timers'
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Input,
  Label,
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

interface EditingState {
  mode: 'edit' | 'create'
  timer: TimerConfig | null
}

export default function Timers() {
  useDocumentTitle('Timers')
  const [timers, setTimers] = useState<TimerConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState<EditingState | null>(null)
  const [formName, setFormName] = useState('')
  const [formInterval, setFormInterval] = useState('')
  const [formMinLines, setFormMinLines] = useState('5')
  const [formTemplate, setFormTemplate] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const templateInputRef = useRef<HTMLInputElement>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      setTimers(await getTimerConfigs())
    } catch {
      setError('無法載入計時器設定')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleToggle = async (timer: TimerConfig) => {
    const newEnabled = !timer.enabled
    setTimers(prev =>
      prev.map(t => (t.timer_name === timer.timer_name ? { ...t, enabled: newEnabled } : t))
    )
    try {
      await toggleTimer(timer.timer_name, newEnabled)
    } catch {
      setTimers(prev =>
        prev.map(t => (t.timer_name === timer.timer_name ? { ...t, enabled: timer.enabled } : t))
      )
    }
  }

  const openCreate = () => {
    setEditing({ mode: 'create', timer: null })
    setFormName('')
    setFormInterval('900')
    setFormMinLines('5')
    setFormTemplate('')
    setFormEnabled(true)
    setSaveError(null)
  }

  const openEditor = (timer: TimerConfig) => {
    setEditing({ mode: 'edit', timer })
    setFormName(timer.timer_name)
    setFormInterval(String(timer.interval_seconds))
    setFormMinLines(String(timer.min_lines))
    setFormTemplate(timer.message_template)
    setFormEnabled(timer.enabled)
    setSaveError(null)
  }

  const insertVariable = (varStr: string) => {
    const input = templateInputRef.current
    if (!input) {
      setFormTemplate(prev => prev + varStr)
      return
    }
    const start = input.selectionStart ?? formTemplate.length
    const end = input.selectionEnd ?? formTemplate.length
    const newValue = formTemplate.slice(0, start) + varStr + formTemplate.slice(end)
    setFormTemplate(newValue)
    requestAnimationFrame(() => {
      input.focus()
      const newPos = start + varStr.length
      input.setSelectionRange(newPos, newPos)
    })
  }

  const handleSave = async () => {
    if (!editing) return
    setSaving(true)
    setSaveError(null)
    try {
      const intervalVal = Number(formInterval)
      if (!intervalVal || intervalVal < 60) {
        setSaveError('間隔時間至少 60 秒')
        return
      }
      if (!formTemplate.trim()) {
        setSaveError('訊息內容不可為空')
        return
      }
      if (editing.mode === 'create') {
        if (!formName.trim()) {
          setSaveError('計時器名稱不可為空')
          return
        }
        const data: TimerCreate = {
          timer_name: formName.trim(),
          interval_seconds: intervalVal,
          min_lines: Number(formMinLines) || 0,
          message_template: formTemplate.trim(),
        }
        const created = await createTimer(data)
        setTimers(prev => [...prev, created])
      } else if (editing.timer) {
        const data: TimerUpdate = {
          interval_seconds: intervalVal,
          min_lines: Number(formMinLines) || 0,
          message_template: formTemplate.trim(),
          enabled: formEnabled,
        }
        const updated = await updateTimer(editing.timer.timer_name, data)
        setTimers(prev => prev.map(t => (t.timer_name === updated.timer_name ? updated : t)))
      }
      setEditing(null)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : '儲存失敗')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (timer: TimerConfig) => {
    try {
      await deleteTimer(timer.timer_name)
      setTimers(prev => prev.filter(t => t.timer_name !== timer.timer_name))
      setEditing(null)
    } catch {
      // Keep sheet open
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
      <div>
        <h1 className="text-page-title font-bold">Timers</h1>
        <p className="text-sub text-muted-foreground">定時訊息 — 直播中定時自動發送設定好的訊息</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>計時器設定</CardTitle>
          <CardDescription>
            計時器在直播進行中按間隔發送訊息，同時需滿足最低聊天行數門檻
          </CardDescription>
          <CardAction>
            <Button size="sm" onClick={openCreate}>
              <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
              新增計時器
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-empty">
              <Spinner className="size-8 text-primary" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-empty text-destructive">
              {error}
            </div>
          ) : (
            <div className="rounded-md border">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[22%]">名稱</TableHead>
                    <TableHead className="w-[12%]">間隔</TableHead>
                    <TableHead className="w-[10%]">最低行數</TableHead>
                    <TableHead>訊息內容</TableHead>
                    <TableHead className="w-[10%] text-center">狀態</TableHead>
                    <TableHead className="w-[10%] text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {timers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground">
                        尚無計時器，點擊「新增計時器」開始設定
                      </TableCell>
                    </TableRow>
                  ) : (
                    timers.map(timer => (
                      <TableRow key={timer.timer_name}>
                        <TableCell className="font-mono font-medium">{timer.timer_name}</TableCell>
                        <TableCell className="text-sub text-muted-foreground">
                          {formatInterval(timer.interval_seconds)}
                        </TableCell>
                        <TableCell className="text-sub text-muted-foreground">
                          {timer.min_lines} 行
                        </TableCell>
                        <TableCell className="text-sub text-muted-foreground truncate max-w-0">
                          {timer.message_template}
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex justify-center">
                            <Switch
                              checked={timer.enabled}
                              onCheckedChange={() => handleToggle(timer)}
                            />
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8"
                            onClick={() => openEditor(timer)}
                          >
                            <Icon icon="fa-solid fa-pen" wrapperClassName="size-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Sheet open={!!editing} onOpenChange={open => !open && setEditing(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>
              {editing?.mode === 'create' ? '新增計時器' : `編輯 ${editing?.timer?.timer_name}`}
            </SheetTitle>
            <SheetDescription>
              {editing?.mode === 'create'
                ? '建立定時訊息，僅在直播中且達到最低行數後觸發'
                : '修改計時器設定'}
            </SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-card px-page">
            {/* Name (create only) */}
            {editing?.mode === 'create' && (
              <div className="flex flex-col gap-2">
                <Label>計時器名稱</Label>
                <Input
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  placeholder="follow-reminder"
                  className="font-mono"
                />
              </div>
            )}

            {/* Interval */}
            <div className="flex flex-col gap-2">
              <Label>間隔時間 (秒)</Label>
              <Input
                type="number"
                min={60}
                step={60}
                value={formInterval}
                onChange={e => setFormInterval(e.target.value)}
                placeholder="900"
                className="w-40"
              />
              <span className="text-label text-muted-foreground">
                最少 60 秒（建議 15 分鐘 = 900 秒）
              </span>
            </div>

            {/* Min Lines */}
            <div className="flex flex-col gap-2">
              <Label>最低聊天行數</Label>
              <Input
                type="number"
                min={0}
                step={1}
                value={formMinLines}
                onChange={e => setFormMinLines(e.target.value)}
                placeholder="5"
                className="w-40"
              />
              <span className="text-label text-muted-foreground">
                間隔內聊天行數未達此值時不觸發，設為 0 則停用門檻
              </span>
            </div>

            {/* Message Template */}
            <div className="flex flex-col gap-2">
              <Label>訊息內容</Label>
              <Input
                ref={templateInputRef}
                value={formTemplate}
                onChange={e => setFormTemplate(e.target.value)}
                placeholder="記得追蹤 $(channel)！"
                className="font-mono text-sub"
              />
              <div className="flex flex-col gap-1.5">
                <span className="text-label text-muted-foreground">可用變數（點擊插入）</span>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    { var: '$(channel)', desc: '頻道名稱' },
                    { var: '$(random 1,100)', desc: '隨機數字' },
                    { var: '$(pick a,b,c)', desc: '隨機選擇' },
                  ].map(({ var: v, desc }) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => insertVariable(v)}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-label font-mono hover:bg-accent transition-colors cursor-pointer"
                    >
                      <span className="text-primary">{v.split(' ')[0]}</span>
                      <span className="text-muted-foreground">— {desc}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Enabled (edit only) */}
            {editing?.mode === 'edit' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <Label>啟用</Label>
                  <span className="text-label text-muted-foreground">關閉後計時器不會觸發</span>
                </div>
                <Switch checked={formEnabled} onCheckedChange={setFormEnabled} />
              </div>
            )}

            {saveError && <p className="text-label text-destructive">{saveError}</p>}
          </div>

          <SheetFooter className="flex-row gap-2">
            {editing?.mode === 'edit' && editing.timer && (
              <Button
                variant="destructive"
                onClick={() => editing.timer && handleDelete(editing.timer)}
              >
                <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
                刪除
              </Button>
            )}
            <div className="flex-1" />
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
