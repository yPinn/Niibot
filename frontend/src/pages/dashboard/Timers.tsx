import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
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
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import { EmptyState, Icon, SlideUp, Spinner } from '@/components/primitives'
import { SortableHead } from '@/components/SortableHead'
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
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

const TIMER_VARS = [
  { var: '$(channel)', desc: '頻道名稱' },
  { var: '$(random 1,100)', desc: '隨機數字' },
  { var: '$(pick a,b,c)', desc: '隨機選擇' },
]

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

interface TimerFormState {
  name: string
  interval: string
  minLines: string
  template: string
  enabled: boolean
  alias: string
  announce: boolean
  showAdvanced: boolean
  saving: boolean
  saveError: string | null
}

type TimerFormAction =
  | {
      type: 'SET'
      field: keyof Omit<TimerFormState, 'saving' | 'saveError'>
      value: TimerFormState[keyof TimerFormState]
    }
  | { type: 'SAVING' }
  | { type: 'SAVE_ERROR'; msg: string }
  | { type: 'SAVE_DONE' }
  | { type: 'RESET'; partial: Partial<TimerFormState> }

const initialTimerForm: TimerFormState = {
  name: '',
  interval: '900',
  minLines: '5',
  template: '',
  enabled: true,
  alias: '',
  announce: false,
  showAdvanced: false,
  saving: false,
  saveError: null,
}

function timerFormReducer(state: TimerFormState, action: TimerFormAction): TimerFormState {
  switch (action.type) {
    case 'SET':
      return { ...state, [action.field]: action.value }
    case 'SAVING':
      return { ...state, saving: true, saveError: null }
    case 'SAVE_ERROR':
      return { ...state, saving: false, saveError: action.msg }
    case 'SAVE_DONE':
      return { ...state, saving: false }
    case 'RESET':
      return { ...initialTimerForm, ...action.partial }
    default:
      return state
  }
}

export default function Timers() {
  useDocumentTitle('Timers')
  const [timers, setTimers] = useState<TimerConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [form, dispatch] = useReducer(timerFormReducer, initialTimerForm)

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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
    dispatch({ type: 'RESET', partial: { interval: '900' } })
  }

  const openEditor = (timer: TimerConfig) => {
    setEditing({ mode: 'edit', timer })
    dispatch({
      type: 'RESET',
      partial: {
        name: timer.timer_name,
        interval: String(timer.interval_seconds),
        minLines: String(timer.min_lines),
        template: timer.message_template,
        enabled: timer.enabled,
        alias: timer.command_alias ?? '',
        announce: timer.announce,
      },
    })
  }

  const { inputRef: templateInputRef, insertText: insertVariable } =
    useInputInsert<HTMLTextAreaElement>(form.template, (val: string) =>
      dispatch({ type: 'SET', field: 'template', value: val })
    )

  const handleSave = async () => {
    if (!editing) return

    // Validate before entering the saving state so we never need to unwind it on validation failure
    const intervalVal = Number(form.interval)
    if (!intervalVal || intervalVal < 60) {
      dispatch({ type: 'SAVE_ERROR', msg: '間隔時間至少 60 秒' })
      return
    }
    if (intervalVal > 86400) {
      dispatch({ type: 'SAVE_ERROR', msg: '間隔時間最多 86400 秒（24 小時）' })
      return
    }
    if (!form.template.trim()) {
      dispatch({ type: 'SAVE_ERROR', msg: '訊息內容不可為空' })
      return
    }
    if (editing.mode === 'create' && !form.name.trim()) {
      dispatch({ type: 'SAVE_ERROR', msg: '計時器名稱不可為空' })
      return
    }

    dispatch({ type: 'SAVING' })
    const aliasValue = form.alias.trim() || null
    try {
      if (editing.mode === 'create') {
        const data: TimerCreate = {
          timer_name: form.name.trim(),
          interval_seconds: intervalVal,
          min_lines: Number(form.minLines) || 0,
          message_template: form.template.trim(),
          announce: form.announce,
          command_alias: aliasValue,
        }
        const created = await createTimer(data)
        setTimers(prev => [...prev, created])
      } else if (editing.timer) {
        const prevAlias = editing.timer.command_alias
        const data: TimerUpdate = {
          interval_seconds: intervalVal,
          min_lines: Number(form.minLines) || 0,
          message_template: form.template.trim(),
          enabled: form.enabled,
          announce: form.announce,
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
      dispatch({ type: 'SAVE_ERROR', msg })
      toast.error('儲存失敗', { description: msg })
    } finally {
      dispatch({ type: 'SAVE_DONE' })
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
    <PageMain>
      <PageHeader title="Timers" description="定時訊息 — 直播中定時自動發送設定好的訊息" />

      <SlideUp inView>
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
              <div className="overflow-x-auto rounded-md border">
                <div className="divide-y divide-border">
                  <div className="flex items-center gap-section px-page py-3 bg-muted/50">
                    <Skeleton className="h-4 w-[20%]" />
                    <Skeleton className="h-4 w-[6%]" />
                    <Skeleton className="h-4 flex-1" />
                    <Skeleton className="h-4 w-[10%]" />
                    <Skeleton className="h-4 w-[8%]" />
                    <Skeleton className="h-4 w-[8%]" />
                  </div>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-section px-page py-3">
                      <Skeleton className="h-4 w-[20%]" />
                      <Skeleton className="h-4 w-[6%]" />
                      <Skeleton className="h-4 flex-1" />
                      <Skeleton className="h-4 w-[10%]" />
                      <Skeleton className="h-8 w-[8%]" />
                      <Skeleton className="h-8 w-[8%]" />
                    </div>
                  ))}
                </div>
              </div>
            ) : error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table className="table-fixed">
                  <TableHeader>
                    <TableRow>
                      <SortableHead
                        className="w-[20%]"
                        sortKey="name"
                        currentKey={sortKey}
                        dir={sortDir}
                        onSort={toggleSort}
                      >
                        名稱
                      </SortableHead>
                      <TableHead className="w-[8%]">類型</TableHead>
                      <TableHead className="hidden md:table-cell">說明</TableHead>
                      <SortableHead
                        className="hidden md:table-cell w-[8%]"
                        sortKey="interval"
                        currentKey={sortKey}
                        dir={sortDir}
                        onSort={toggleSort}
                      >
                        間隔
                      </SortableHead>
                      <SortableHead
                        className="w-[8%] text-center"
                        sortKey="enabled"
                        currentKey={sortKey}
                        dir={sortDir}
                        onSort={toggleSort}
                      >
                        狀態
                      </SortableHead>
                      <TableHead className="w-[7%] text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sorted.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6}>
                          <EmptyState
                            icon="fa-solid fa-clock"
                            title="尚無計時器"
                            description="點擊「新增計時器」開始設定"
                          />
                        </TableCell>
                      </TableRow>
                    ) : (
                      sorted.map(timer => {
                        const isBuiltin = timer.id !== null && timer.id < 0
                        return (
                          <TableRow key={timer.timer_name}>
                            <TableCell className="font-mono font-medium">
                              <div className="flex items-center gap-1.5">
                                <span>{timer.timer_name}</span>
                                {timer.announce && (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span className="cursor-default text-muted-foreground">
                                        <Icon
                                          icon="fa-solid fa-bullhorn"
                                          wrapperClassName="size-3"
                                        />
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
                            <TableCell>
                              {isBuiltin && (
                                <Badge variant="secondary" className="text-label font-normal">
                                  內建
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell className="hidden md:table-cell max-w-0 truncate text-sub text-muted-foreground">
                              {timer.message_template}
                            </TableCell>
                            <TableCell className="hidden md:table-cell text-sub text-muted-foreground">
                              {formatInterval(timer.interval_seconds)}
                            </TableCell>
                            <TableCell className="text-center">
                              <Switch
                                checked={timer.enabled}
                                onCheckedChange={() => handleToggle(timer)}
                              />
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
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      <Sheet open={!!editing} onOpenChange={open => !open && setEditing(null)}>
        <SheetContent className="gap-section">
          <SheetHeader>
            <SheetTitle>
              {editing?.mode === 'create' ? '新增計時器' : `編輯 ${editing?.timer?.timer_name}`}
            </SheetTitle>
            <SheetDescription>
              {editing?.mode === 'create' ? '直播進行中按設定間隔自動發送訊息' : '修改計時器設定'}
            </SheetDescription>
          </SheetHeader>

          <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
            {editing?.mode === 'create' && (
              <div className="flex flex-col gap-2">
                <Label htmlFor="timer-name">計時器名稱</Label>
                <Input
                  id="timer-name"
                  value={form.name}
                  onChange={e => dispatch({ type: 'SET', field: 'name', value: e.target.value })}
                  placeholder="follow-reminder"
                  className="font-mono"
                  autoFocus
                />
                <span className="text-label text-muted-foreground">
                  唯一識別名稱，建立後無法修改
                </span>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <Label htmlFor="timer-template">訊息內容</Label>
              <Textarea
                id="timer-template"
                ref={templateInputRef}
                value={form.template}
                onChange={e => dispatch({ type: 'SET', field: 'template', value: e.target.value })}
                placeholder="記得追蹤 $(channel)！"
                className="font-mono text-sub"
                autoFocus={editing?.mode === 'edit'}
              />
              <VariableInserter variables={TIMER_VARS} onInsert={insertVariable} />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="timer-interval">間隔時間 (秒)</Label>
              <Input
                id="timer-interval"
                type="number"
                min={60}
                max={86400}
                step={60}
                value={form.interval}
                onChange={e => dispatch({ type: 'SET', field: 'interval', value: e.target.value })}
                placeholder="900"
                className="w-24"
              />
              <span className="text-label text-muted-foreground">
                最少 60 秒，建議 15 分鐘（900 秒）以上
              </span>
            </div>

            {editing?.mode === 'edit' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <span className="text-sub font-medium leading-none">啟用</span>
                  <span className="text-label text-muted-foreground">關閉後不會觸發</span>
                </div>
                <Switch
                  aria-label="啟用"
                  checked={form.enabled}
                  onCheckedChange={v => dispatch({ type: 'SET', field: 'enabled', value: v })}
                />
              </div>
            )}

            <Button
              variant="ghost"
              size="sm"
              className="w-fit px-0 text-muted-foreground hover:text-foreground hover:bg-transparent"
              onClick={() =>
                dispatch({ type: 'SET', field: 'showAdvanced', value: !form.showAdvanced })
              }
            >
              <Icon
                icon={form.showAdvanced ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                wrapperClassName="size-3"
              />
              {form.showAdvanced ? '隱藏進階設定' : '顯示進階設定'}
            </Button>

            {form.showAdvanced && (
              <div className="flex flex-col gap-card border-l-2 border-muted pl-page">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="timer-min-lines">最低聊天行數</Label>
                  <Input
                    id="timer-min-lines"
                    type="number"
                    min={0}
                    step={1}
                    value={form.minLines}
                    onChange={e =>
                      dispatch({ type: 'SET', field: 'minLines', value: e.target.value })
                    }
                    placeholder="5"
                    className="w-24"
                  />
                  <span className="text-label text-muted-foreground">
                    低於此值時跳過，0 則不限制
                  </span>
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="timer-alias">別名</Label>
                  <Input
                    id="timer-alias"
                    value={form.alias}
                    onChange={e => dispatch({ type: 'SET', field: 'alias', value: e.target.value })}
                    placeholder="socials"
                    className="font-mono text-sub"
                  />
                  <span className="text-label text-muted-foreground">
                    用 !別名 手動觸發，同時重置自動計時
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex flex-col gap-0.5">
                    <span className="flex items-center gap-1.5 text-sub font-medium leading-none">
                      公告模式
                      <Badge variant="secondary" className="text-label">
                        需要管理員
                      </Badge>
                    </span>
                    <span className="text-label text-muted-foreground">
                      以聊天室公告方式發送，訊息會被高亮顯示
                    </span>
                  </div>
                  <Switch
                    aria-label="公告模式"
                    checked={form.announce}
                    onCheckedChange={v => dispatch({ type: 'SET', field: 'announce', value: v })}
                  />
                </div>
              </div>
            )}

            {form.saveError && <p className="text-label text-destructive">{form.saveError}</p>}
          </div>

          <SheetFooter className="shrink-0 flex-row gap-2">
            {editing?.mode === 'edit' &&
              editing.timer &&
              editing.timer.id !== null &&
              editing.timer.id > 0 && (
                <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
                  <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
                  刪除
                </Button>
              )}
            <div className="flex-1" />
            <SheetClose asChild>
              <Button variant="outline">取消</Button>
            </SheetClose>
            <Button onClick={handleSave} disabled={form.saving}>
              {form.saving && <Spinner className="mr-1.5" />}
              儲存
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <DeleteConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="確定刪除計時器？"
        description={
          <>
            即將刪除計時器「
            <span className="font-medium text-foreground">{editing?.timer?.timer_name}</span>
            」，此操作無法還原。
          </>
        }
        onConfirm={() => editing?.timer && handleDelete(editing.timer)}
      />
    </PageMain>
  )
}
