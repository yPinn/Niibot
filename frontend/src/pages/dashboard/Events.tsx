import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type EventConfig,
  getEventConfigs,
  getRedemptionConfigs,
  getTwitchRewards,
  type RedemptionConfig,
  toggleEventConfig,
  type TwitchReward,
  updateEventConfig,
  updateRedemptionConfig,
} from '@/api/events'
import { AffiliateLockOverlay } from '@/components/AffiliateLockOverlay'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import { SortableHead } from '@/components/SortableHead'
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  Icon,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Skeleton,
  SlideUp,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useInputInsert } from '@/hooks/useInputInsert'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'

const TEMPLATE_VARIABLES: Record<string, { var: string; desc: string }[]> = {
  follow: [{ var: '$(user)', desc: '追隨者名稱' }],
  subscribe: [
    { var: '$(user)', desc: '訂閱者名稱' },
    { var: '$(tier)', desc: '訂閱等級 (T1/T2/T3)' },
  ],
  raid: [
    { var: '$(user)', desc: '揪團者名稱' },
    { var: '$(count)', desc: '觀眾數量' },
  ],
  bits: [
    { var: '$(user)', desc: '投擲者名稱' },
    { var: '$(amount)', desc: '小奇點數量' },
  ],
}

const EVENT_TYPE_COLORS: Record<string, string> = {
  follow: 'bg-status-info/10 text-status-info',
  subscribe: 'bg-status-special/10 text-status-special',
  raid: 'bg-status-offline/10 text-status-offline',
  bits: 'bg-status-loading/10 text-status-loading',
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  follow: '追隨',
  subscribe: '訂閱',
  raid: '揪團',
  bits: '小奇點',
}

const EVENT_TYPE_NAMES: Record<string, string> = {
  follow: '追隨感謝',
  subscribe: '訂閱感謝',
  raid: '揪團訊息',
  bits: '小奇點感謝',
}

const EVENT_TYPE_ORDER: string[] = ['follow', 'subscribe', 'bits', 'raid']

const ACTION_TYPE_LABELS: Record<string, string> = {
  vip: 'VIP 授予',
  first: '本日頭香',
  niibot_auth: 'Niibot 授權',
  game_queue: '遊戲排隊券',
  video_queue: '播放清單',
}

type EventSortKey = 'event_type' | 'type_label' | 'trigger_count' | 'enabled'
type RedemptionSortKey = 'action_type' | 'reward_name' | 'enabled'

export default function Events() {
  useDocumentTitle('Events')
  const { isAffiliate } = useAuth()
  const [events, setEvents] = useState<EventConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editingEvent, setEditingEvent] = useState<EventConfig | null>(null)
  const [editTemplate, setEditTemplate] = useState('')
  const [editEnabled, setEditEnabled] = useState(true)
  const [editOptions, setEditOptions] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)

  const eventSort = useSortState<EventSortKey>('event_type')
  const redSort = useSortState<RedemptionSortKey>('action_type')

  const [redemptions, setRedemptions] = useState<RedemptionConfig[]>([])
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)

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

  const fetchRedemptions = useCallback(async () => {
    try {
      const configsPromise = getRedemptionConfigs()
      const rewardsPromise = isAffiliate
        ? getTwitchRewards().catch(() => [] as TwitchReward[])
        : Promise.resolve([] as TwitchReward[])
      const [configs, rewards] = await Promise.all([configsPromise, rewardsPromise])
      setRedemptions(configs)
      setTwitchRewards([...rewards].sort((a, b) => a.cost - b.cost))
    } catch {
      // Silently fail — configs may not be available
    } finally {
      setRedemptionLoading(false)
    }
  }, [isAffiliate])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchEvents()

    fetchRedemptions()
  }, [fetchEvents, fetchRedemptions])

  const { sortKey: eventSortKey, sortDir: eventSortDir } = eventSort
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => {
      let cmp = 0
      switch (eventSortKey) {
        case 'event_type': {
          const ai = EVENT_TYPE_ORDER.indexOf(a.event_type)
          const bi = EVENT_TYPE_ORDER.indexOf(b.event_type)
          cmp = (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
          break
        }
        case 'type_label':
          cmp = (EVENT_TYPE_LABELS[a.event_type] || a.event_type).localeCompare(
            EVENT_TYPE_LABELS[b.event_type] || b.event_type
          )
          break
        case 'trigger_count':
          cmp = a.trigger_count - b.trigger_count
          break
        case 'enabled':
          cmp = Number(a.enabled) - Number(b.enabled)
          break
      }
      return eventSortDir === 'desc' ? -cmp : cmp
    })
  }, [events, eventSortKey, eventSortDir])

  const { sortKey: redSortKey, sortDir: redSortDir } = redSort
  const sortedRedemptions = useMemo(() => {
    return [...redemptions].sort((a, b) => {
      let cmp = 0
      switch (redSortKey) {
        case 'action_type':
          cmp = (ACTION_TYPE_LABELS[a.action_type] || a.action_type).localeCompare(
            ACTION_TYPE_LABELS[b.action_type] || b.action_type
          )
          break
        case 'reward_name':
          cmp = a.reward_name.localeCompare(b.reward_name)
          break
        case 'enabled':
          cmp = Number(a.enabled) - Number(b.enabled)
          break
      }
      return redSortDir === 'desc' ? -cmp : cmp
    })
  }, [redemptions, redSortKey, redSortDir])

  const { toggle: handleToggle } = useOptimisticToggle<EventConfig>({
    setState: setEvents,
    getId: e => e.event_type,
    toggleFn: (e, enabled) => toggleEventConfig(e.event_type, enabled).then(() => {}),
    messages: { on: '事件已啟用', off: '事件已停用', error: '切換事件狀態失敗' },
  })

  const { toggle: handleRedemptionToggle } = useOptimisticToggle<RedemptionConfig>({
    setState: setRedemptions,
    getId: r => r.action_type,
    toggleFn: (r, enabled) =>
      updateRedemptionConfig(r.action_type, { reward_name: r.reward_name, enabled }).then(() => {}),
    messages: { on: '兌換已啟用', off: '兌換已停用', error: '切換兌換狀態失敗' },
  })

  const { inputRef: templateInputRef, insertText: insertVariable } = useInputInsert(
    editTemplate,
    setEditTemplate
  )

  const openEditor = (event: EventConfig) => {
    setEditingEvent(event)
    setEditTemplate(event.message_template)
    setEditEnabled(event.enabled)
    setEditOptions(event.options ?? {})
  }

  const handleSave = async () => {
    if (!editingEvent) return
    setSaving(true)
    try {
      const updated = await updateEventConfig(editingEvent.event_type, {
        message_template: editTemplate,
        enabled: editEnabled,
        options: editOptions,
      })
      setEvents(prev => prev.map(e => (e.event_type === updated.event_type ? updated : e)))
      toast.success('事件設定已儲存')
      setEditingEvent(null)
    } catch {
      toast.error('儲存事件設定失敗')
    } finally {
      setSaving(false)
    }
  }

  const handleRewardSelect = async (red: RedemptionConfig, rewardTitle: string) => {
    try {
      const updated = await updateRedemptionConfig(red.action_type, {
        reward_name: rewardTitle,
        enabled: red.enabled,
      })
      setRedemptions(prev => prev.map(r => (r.action_type === updated.action_type ? updated : r)))
      toast.success('忠誠點數獎勵已更新')
    } catch {
      toast.error('更新忠誠點數獎勵失敗')
    }
  }

  return (
    <PageMain>
      <PageHeader title="Events" description="管理頻道事件、自動回應與忠誠點數兌換" />

      <SlideUp inView>
        <Card>
          <CardHeader>
            <CardTitle>事件列表</CardTitle>
            <CardDescription>設定頻道事件觸發時的自動回應訊息</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
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
                        sortKey="event_type"
                        currentKey={eventSort.sortKey}
                        dir={eventSort.sortDir}
                        onSort={eventSort.toggleSort}
                      >
                        事件名稱
                      </SortableHead>
                      <SortableHead
                        className="hidden md:table-cell w-[12%]"
                        sortKey="type_label"
                        currentKey={eventSort.sortKey}
                        dir={eventSort.sortDir}
                        onSort={eventSort.toggleSort}
                      >
                        類型
                      </SortableHead>
                      <TableHead className="hidden md:table-cell">訊息模板</TableHead>
                      <SortableHead
                        className="hidden md:table-cell w-[12%] text-right"
                        sortKey="trigger_count"
                        currentKey={eventSort.sortKey}
                        dir={eventSort.sortDir}
                        onSort={eventSort.toggleSort}
                      >
                        觸發次數
                      </SortableHead>
                      <SortableHead
                        className="w-[10%] text-center"
                        sortKey="enabled"
                        currentKey={eventSort.sortKey}
                        dir={eventSort.sortDir}
                        onSort={eventSort.toggleSort}
                      >
                        狀態
                      </SortableHead>
                      <TableHead className="w-[8%] text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedEvents.map(event => {
                      const locked =
                        !isAffiliate &&
                        (event.event_type === 'subscribe' || event.event_type === 'bits')
                      return (
                        <TableRow key={event.event_type} className={locked ? 'opacity-50' : ''}>
                          <TableCell className="font-medium">
                            <span className="flex items-center gap-1.5">
                              {EVENT_TYPE_NAMES[event.event_type] || event.event_type}
                              {locked && (
                                <Icon icon="fa-solid fa-lock" wrapperClassName="size-3.5" />
                              )}
                            </span>
                          </TableCell>
                          <TableCell className="hidden md:table-cell">
                            <Badge className={EVENT_TYPE_COLORS[event.event_type] || ''}>
                              {EVENT_TYPE_LABELS[event.event_type] || event.event_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="hidden md:table-cell max-w-0 truncate font-mono text-label">
                            {locked ? (
                              <span className="text-muted-foreground">
                                需要聯盟夥伴或合作夥伴資格
                              </span>
                            ) : (
                              event.message_template
                            )}
                          </TableCell>
                          <TableCell className="hidden md:table-cell text-right">
                            {event.trigger_count}
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="flex justify-center">
                              <Switch
                                checked={event.enabled}
                                onCheckedChange={() => handleToggle(event)}
                                disabled={locked}
                              />
                            </div>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openEditor(event)}
                              disabled={locked}
                            >
                              編輯
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      <SlideUp inView delay={0.1}>
        <Card className="relative overflow-hidden">
          {!isAffiliate && (
            <AffiliateLockOverlay
              message="成為 Twitch 聯盟夥伴或合作夥伴後即可設定忠誠點數獎勵"
              className="rounded-[inherit]"
            />
          )}
          <CardHeader>
            <CardTitle>忠誠點數兌換</CardTitle>
            <CardDescription>選擇 Twitch 忠誠點數獎勵對應的動作</CardDescription>
          </CardHeader>
          <CardContent>
            {redemptionLoading ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : !isAffiliate ? (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia>
                    <Icon icon="fa-solid fa-lock" wrapperClassName="size-6" />
                  </EmptyMedia>
                  <EmptyDescription>
                    成為 Twitch 聯盟夥伴或合作夥伴後即可設定忠誠點數獎勵
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortableHead
                        sortKey="action_type"
                        currentKey={redSort.sortKey}
                        dir={redSort.sortDir}
                        onSort={redSort.toggleSort}
                      >
                        動作
                      </SortableHead>
                      <SortableHead
                        sortKey="reward_name"
                        currentKey={redSort.sortKey}
                        dir={redSort.sortDir}
                        onSort={redSort.toggleSort}
                      >
                        獎勵名稱
                      </SortableHead>
                      <SortableHead
                        className="text-center"
                        sortKey="enabled"
                        currentKey={redSort.sortKey}
                        dir={redSort.sortDir}
                        onSort={redSort.toggleSort}
                      >
                        狀態
                      </SortableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedRedemptions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-center text-muted-foreground">
                          尚無兌換設定
                        </TableCell>
                      </TableRow>
                    ) : (
                      sortedRedemptions.map(red => (
                        <TableRow key={red.action_type}>
                          <TableCell className="font-medium">
                            {ACTION_TYPE_LABELS[red.action_type] || red.action_type}
                          </TableCell>
                          <TableCell>
                            {twitchRewards.length === 0 ? (
                              <span className="text-sub text-muted-foreground">
                                請先在 Twitch 建立自訂獎勵
                              </span>
                            ) : (
                              <Select
                                value={red.reward_name || '__none__'}
                                onValueChange={v =>
                                  handleRewardSelect(red, v === '__none__' ? '' : v)
                                }
                              >
                                <SelectTrigger size="sm" className="w-full md:max-w-56">
                                  <SelectValue placeholder="選擇獎勵..." />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__" className="text-muted-foreground">
                                    未選擇
                                  </SelectItem>
                                  {twitchRewards.map(reward => (
                                    <SelectItem key={reward.id} value={reward.title}>
                                      {reward.title} ({reward.cost.toLocaleString()} 點)
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="flex justify-center">
                              <Switch
                                checked={red.enabled}
                                onCheckedChange={() => handleRedemptionToggle(red)}
                              />
                            </div>
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
      </SlideUp>

      <Sheet open={!!editingEvent} onOpenChange={open => !open && setEditingEvent(null)}>
        <SheetContent className="gap-section">
          <SheetHeader>
            <SheetTitle>
              編輯{' '}
              {editingEvent
                ? EVENT_TYPE_NAMES[editingEvent.event_type] || editingEvent.event_type
                : ''}
            </SheetTitle>
            <SheetDescription>修改事件觸發時的自動回應訊息</SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-card px-page">
            <div className="flex flex-col gap-2">
              <Label htmlFor="event-template">訊息模板</Label>
              <Input
                id="event-template"
                ref={templateInputRef}
                value={editTemplate}
                onChange={e => setEditTemplate(e.target.value)}
                placeholder="輸入回應訊息..."
                className="font-mono text-sub"
              />

              {editingEvent && TEMPLATE_VARIABLES[editingEvent.event_type] && (
                <VariableInserter
                  variables={TEMPLATE_VARIABLES[editingEvent.event_type]}
                  onInsert={insertVariable}
                />
              )}
            </div>

            {editingEvent?.event_type === 'raid' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <span className="flex items-center gap-1.5 text-sm font-medium leading-none">
                    自動推薦
                    <Badge variant="secondary" className="text-label">
                      需要管理員
                    </Badge>
                  </span>
                  <span className="text-label text-muted-foreground">
                    揪團時自動執行 /shoutout 展示對方頻道
                  </span>
                </div>
                <Switch
                  aria-label="自動推薦"
                  checked={(editOptions.auto_shoutout as boolean) ?? true}
                  onCheckedChange={v => setEditOptions(prev => ({ ...prev, auto_shoutout: v }))}
                />
              </div>
            )}

            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="text-sm font-medium leading-none">啟用</span>
                <span className="text-label text-muted-foreground">
                  關閉後事件觸發時不會發送訊息
                </span>
              </div>
              <Switch aria-label="啟用" checked={editEnabled} onCheckedChange={setEditEnabled} />
            </div>
          </div>

          <SheetFooter className="flex-row justify-end gap-2">
            <SheetClose asChild>
              <Button variant="outline">取消</Button>
            </SheetClose>
            <Button onClick={handleSave} disabled={saving}>
              {saving && <Spinner className="mr-1.5" />}
              儲存
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </PageMain>
  )
}
