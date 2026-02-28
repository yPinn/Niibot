import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

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
import { PageHeader } from '@/components/PageHeader'
import { SortableHead } from '@/components/SortableHead'
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useInputInsert } from '@/hooks/useInputInsert'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'
import { nameSort } from '@/lib/sort'

type TimerSortKey = 'name' | 'interval' | 'enabled'

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

  // TODO: The form state below (editing, formName, formInterval, formMinLines, formTemplate,
  // formEnabled, formAlias, showAdvanced, saving, saveError) should be refactored to a single
  // useReducer for consistency with CommandSheet. Deferred due to risk/scope.
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [formName, setFormName] = useState('')
  const [formInterval, setFormInterval] = useState('')
  const [formMinLines, setFormMinLines] = useState('5')
  const [formTemplate, setFormTemplate] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [formAlias, setFormAlias] = useState('')
  const [formAnnounce, setFormAnnounce] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const timerSort = useSortState<TimerSortKey>('name')

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

  const { toggle: handleToggle } = useOptimisticToggle<TimerConfig>({
    setState: setTimers,
    getId: t => t.timer_name,
    toggleFn: (t, enabled) => toggleTimer(t.timer_name, enabled).then(() => {}),
    messages: { on: '計時器已啟用', off: '計時器已停用', error: '切換計時器狀態失敗' },
  })

  const sorted = useMemo(() => {
    const { sortKey, sortDir } = timerSort
    return [...timers].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'name':
          cmp = nameSort(a.timer_name, b.timer_name)
          break
        case 'interval':
          cmp = a.interval_seconds - b.interval_seconds
          break
        case 'enabled':
          cmp = Number(a.enabled) - Number(b.enabled)
          break
      }
      return sortDir === 'desc' ? -cmp : cmp
    })
  }, [timers, timerSort])

  const openCreate = () => {
    setEditing({ mode: 'create', timer: null })
    setFormName('')
    setFormInterval('900')
    setFormMinLines('5')
    setFormTemplate('')
    setFormEnabled(true)
    setFormAlias('')
    setFormAnnounce(false)
    setShowAdvanced(false)
    setSaveError(null)
  }

  const openEditor = (timer: TimerConfig) => {
    setEditing({ mode: 'edit', timer })
    setFormName(timer.timer_name)
    setFormInterval(String(timer.interval_seconds))
    setFormMinLines(String(timer.min_lines))
    setFormTemplate(timer.message_template)
    setFormEnabled(timer.enabled)
    setFormAlias(timer.command_alias ?? '')
    setFormAnnounce(timer.announce)
    setShowAdvanced(false)
    setSaveError(null)
  }

  const { inputRef: templateInputRef, insertText: insertVariable } = useInputInsert(
    formTemplate,
    setFormTemplate
  )

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
      const aliasValue = formAlias.trim() || null
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
          announce: formAnnounce,
          command_alias: aliasValue,
        }
        const created = await createTimer(data)
        setTimers(prev => [...prev, created])
      } else if (editing.timer) {
        const prevAlias = editing.timer.command_alias
        const data: TimerUpdate = {
          interval_seconds: intervalVal,
          min_lines: Number(formMinLines) || 0,
          message_template: formTemplate.trim(),
          enabled: formEnabled,
          announce: formAnnounce,
          command_alias: aliasValue,
          clear_alias: prevAlias !== null && aliasValue === null,
        }
        const updated = await updateTimer(editing.timer.timer_name, data)
        setTimers(prev => prev.map(t => (t.timer_name === updated.timer_name ? updated : t)))
      }
      toast.success(editing.mode === 'create' ? '計時器已建立' : '計時器已更新')
      setEditing(null)
    } catch (e) {
      const msg = e instanceof Error ? e.message : '儲存失敗'
      setSaveError(msg)
      toast.error('儲存失敗', { description: msg })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (timer: TimerConfig) => {
    try {
      await deleteTimer(timer.timer_name)
      setTimers(prev => prev.filter(t => t.timer_name !== timer.timer_name))
      setEditing(null)
      toast.success('計時器已刪除')
    } catch {
      toast.error('刪除計時器失敗')
    }
  }

  const { sortKey, sortDir, toggleSort } = timerSort

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <PageHeader title="Timers" description="定時訊息 — 直播中定時自動發送設定好的訊息" />

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
            <div className="overflow-x-auto rounded-md border">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    <SortableHead
                      className="w-[24%]"
                      sortKey="name"
                      currentKey={sortKey}
                      dir={sortDir}
                      onSort={toggleSort}
                    >
                      名稱
                    </SortableHead>
                    <TableHead>訊息內容</TableHead>
                    <SortableHead
                      className="w-[12%]"
                      sortKey="interval"
                      currentKey={sortKey}
                      dir={sortDir}
                      onSort={toggleSort}
                    >
                      間隔
                    </SortableHead>
                    <SortableHead
                      className="w-[10%] text-center"
                      sortKey="enabled"
                      currentKey={sortKey}
                      dir={sortDir}
                      onSort={toggleSort}
                    >
                      狀態
                    </SortableHead>
                    <TableHead className="w-[10%] text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sorted.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        尚無計時器，點擊「新增計時器」開始設定
                      </TableCell>
                    </TableRow>
                  ) : (
                    sorted.map(timer => (
                      <TableRow key={timer.timer_name}>
                        <TableCell className="font-mono font-medium">
                          <div className="flex items-center gap-1.5">
                            <span>{timer.timer_name}</span>
                            {timer.announce && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="cursor-default text-muted-foreground">
                                    <Icon icon="fa-solid fa-bullhorn" wrapperClassName="size-3" />
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>以公告方式發送</TooltipContent>
                              </Tooltip>
                            )}
                            {timer.command_alias && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="cursor-default text-muted-foreground">
                                    <Icon icon="fa-solid fa-bolt" wrapperClassName="size-3" />
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <span className="font-mono">!{timer.command_alias}</span>
                                  <span className="ml-1 text-muted-foreground">可手動觸發</span>
                                </TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="max-w-0 truncate text-sub text-muted-foreground">
                          {timer.message_template}
                        </TableCell>
                        <TableCell className="text-sub text-muted-foreground">
                          {formatInterval(timer.interval_seconds)}
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
              {editing?.mode === 'create' ? '直播進行中按設定間隔自動發送訊息' : '修改計時器設定'}
            </SheetDescription>
          </SheetHeader>

          <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
            {/* Name (create only) */}
            {editing?.mode === 'create' && (
              <div className="flex flex-col gap-2">
                <Label>計時器名稱</Label>
                <Input
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  placeholder="follow-reminder"
                  className="font-mono"
                  autoFocus
                />
                <span className="text-label text-muted-foreground">
                  唯一識別名稱，建立後無法修改
                </span>
              </div>
            )}

            {/* Message Template */}
            <div className="flex flex-col gap-2">
              <Label>訊息內容</Label>
              <Input
                ref={templateInputRef}
                value={formTemplate}
                onChange={e => setFormTemplate(e.target.value)}
                placeholder="記得追蹤 $(channel)！"
                className="font-mono text-sub"
                autoFocus={editing?.mode === 'edit'}
              />
              <VariableInserter
                variables={[
                  { var: '$(channel)', desc: '頻道名稱' },
                  { var: '$(random 1,100)', desc: '隨機數字' },
                  { var: '$(pick a,b,c)', desc: '隨機選擇' },
                ]}
                onInsert={insertVariable}
              />
            </div>

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
                className="w-24"
              />
              <span className="text-label text-muted-foreground">
                最少 60 秒，建議 15 分鐘（900 秒）以上
              </span>
            </div>

            {/* Enabled (edit only) */}
            {editing?.mode === 'edit' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <Label>啟用</Label>
                  <span className="text-label text-muted-foreground">關閉後不會觸發</span>
                </div>
                <Switch checked={formEnabled} onCheckedChange={setFormEnabled} />
              </div>
            )}

            {/* Advanced toggle */}
            <button
              type="button"
              className="flex cursor-pointer items-center gap-2 text-sub text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setShowAdvanced(v => !v)}
            >
              <Icon
                icon={showAdvanced ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                wrapperClassName="size-3"
              />
              {showAdvanced ? '隱藏進階設定' : '顯示進階設定'}
            </button>

            {showAdvanced && (
              <div className="flex flex-col gap-card border-l-2 border-muted pl-page">
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
                    className="w-24"
                  />
                  <span className="text-label text-muted-foreground">
                    低於此值時跳過，0 則不限制
                  </span>
                </div>

                {/* Command Alias */}
                <div className="flex flex-col gap-2">
                  <Label>別名</Label>
                  <Input
                    value={formAlias}
                    onChange={e => setFormAlias(e.target.value)}
                    placeholder="socials"
                    className="font-mono text-sub"
                  />
                  <span className="text-label text-muted-foreground">
                    用 !別名 手動觸發，同時重置自動計時
                  </span>
                </div>

                {/* Announce mode */}
                <div className="flex items-center justify-between">
                  <div className="flex flex-col gap-0.5">
                    <Label>公告模式</Label>
                    <span className="text-label text-muted-foreground">
                      以聊天室公告方式發送，訊息會被高亮顯示
                    </span>
                  </div>
                  <Switch checked={formAnnounce} onCheckedChange={setFormAnnounce} />
                </div>
              </div>
            )}

            {saveError && <p className="text-label text-destructive">{saveError}</p>}
          </div>

          <SheetFooter className="shrink-0 flex-row gap-2">
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
