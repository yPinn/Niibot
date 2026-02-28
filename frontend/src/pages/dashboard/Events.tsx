import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type EventConfig,
  getEventConfigs,
  getRedemptionConfigs,
  getTwitchRewards,
  NonPartnerError,
  type RedemptionConfig,
  toggleEventConfig,
  type TwitchReward,
  updateEventConfig,
  updateRedemptionConfig,
} from '@/api/events'
import { PageHeader } from '@/components/PageHeader'
import { SortableHead } from '@/components/SortableHead'
import {
  Badge,
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
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useInputInsert } from '@/hooks/useInputInsert'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'

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
  bits: [
    { var: '$(user)', desc: '投擲者名稱' },
    { var: '$(amount)', desc: 'Bits 數量' },
  ],
}

interface BitsTier {
  min_bits: number
  max_bits: number | null
  message: string
}

const EVENT_TYPE_COLORS: Record<string, string> = {
  follow: 'bg-status-info/10 text-status-info',
  subscribe: 'bg-status-special/10 text-status-special',
  raid: 'bg-status-offline/10 text-status-offline',
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  follow: '追隨',
  subscribe: '訂閱',
  raid: 'Raid',
}

const EVENT_TYPE_NAMES: Record<string, string> = {
  follow: '追隨感謝',
  subscribe: '訂閱感謝',
  raid: '揪團訊息',
}

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
  const [events, setEvents] = useState<EventConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Sheet editing state
  const [editingEvent, setEditingEvent] = useState<EventConfig | null>(null)
  const [editTemplate, setEditTemplate] = useState('')
  const [editEnabled, setEditEnabled] = useState(true)
  const [editOptions, setEditOptions] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)

  // Sort states
  const eventSort = useSortState<EventSortKey>('event_type')
  const redSort = useSortState<RedemptionSortKey>('action_type')

  // Redemption state
  const [redemptions, setRedemptions] = useState<RedemptionConfig[]>([])
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [isNonPartner, setIsNonPartner] = useState(false)

  // Bits tier state
  const [bitsTiers, setBitsTiers] = useState<BitsTier[]>([])
  const [newTierMin, setNewTierMin] = useState('')
  const [newTierMax, setNewTierMax] = useState('')
  const [newTierMsg, setNewTierMsg] = useState('')
  const [bitsSaving, setBitsSaving] = useState(false)

  const fetchEvents = useCallback(async () => {
    try {
      setError(null)
      const data = await getEventConfigs()
      setEvents(data)
      const bitsConfig = data.find(e => e.event_type === 'bits')
      if (bitsConfig) {
        setBitsTiers((bitsConfig.options as { tiers?: BitsTier[] }).tiers ?? [])
      }
    } catch {
      setError('無法載入事件設定')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchRedemptions = useCallback(async () => {
    try {
      const configsPromise = getRedemptionConfigs()
      const rewardsPromise = getTwitchRewards().catch(e => {
        if (e instanceof NonPartnerError) setIsNonPartner(true)
        return [] as TwitchReward[]
      })
      const [configs, rewards] = await Promise.all([configsPromise, rewardsPromise])
      setRedemptions(configs)
      setTwitchRewards([...rewards].sort((a, b) => a.cost - b.cost))
    } catch {
      // Silently fail — configs may not be available
    } finally {
      setRedemptionLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchEvents()
    fetchRedemptions()
  }, [fetchEvents, fetchRedemptions])

  const bitsConfig = useMemo(() => events.find(e => e.event_type === 'bits') ?? null, [events])

  const sortedEvents = useMemo(() => {
    const { sortKey, sortDir } = eventSort
    return [...events]
      .filter(e => e.event_type !== 'bits')
      .sort((a, b) => {
        let cmp = 0
        switch (sortKey) {
          case 'event_type':
            cmp = (EVENT_TYPE_NAMES[a.event_type] || a.event_type).localeCompare(
              EVENT_TYPE_NAMES[b.event_type] || b.event_type
            )
            break
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
        return sortDir === 'desc' ? -cmp : cmp
      })
  }, [events, eventSort])

  const sortedRedemptions = useMemo(() => {
    const { sortKey, sortDir } = redSort
    return [...redemptions].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
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
      return sortDir === 'desc' ? -cmp : cmp
    })
  }, [redemptions, redSort])

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

  // Non-partner detection — determined by 403 from Twitch API, not by empty rewards

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

  // --- Bits handlers ---

  const handleBitsToggle = async (enabled: boolean) => {
    if (!bitsConfig) return
    try {
      const updated = await updateEventConfig('bits', {
        message_template: bitsConfig.message_template,
        enabled,
        options: bitsConfig.options,
      })
      setEvents(prev => prev.map(e => (e.event_type === 'bits' ? updated : e)))
      toast.success(enabled ? 'Bits 事件已啟用' : 'Bits 事件已停用')
    } catch {
      toast.error('切換 Bits 事件失敗')
    }
  }

  const handleAddBitsTier = () => {
    const min = parseInt(newTierMin, 10)
    const max = newTierMax.trim() === '' ? null : parseInt(newTierMax, 10)
    if (isNaN(min) || min < 1) {
      toast.error('最低 Bits 需 >= 1')
      return
    }
    if (max !== null && (isNaN(max) || max < min)) {
      toast.error('最高 Bits 需大於最低 Bits')
      return
    }
    if (!newTierMsg.trim()) {
      toast.error('請輸入訊息模板')
      return
    }
    setBitsTiers(prev => [...prev, { min_bits: min, max_bits: max, message: newTierMsg.trim() }])
    setNewTierMin('')
    setNewTierMax('')
    setNewTierMsg('')
  }

  const handleRemoveBitsTier = (idx: number) => {
    setBitsTiers(prev => prev.filter((_, i) => i !== idx))
  }

  const handleSaveBitsTiers = async () => {
    if (!bitsConfig) return
    setBitsSaving(true)
    try {
      const updated = await updateEventConfig('bits', {
        message_template: bitsConfig.message_template,
        enabled: bitsConfig.enabled,
        options: { ...bitsConfig.options, tiers: bitsTiers },
      })
      setEvents(prev => prev.map(e => (e.event_type === 'bits' ? updated : e)))
      toast.success('Bits 分級設定已儲存')
    } catch {
      toast.error('儲存 Bits 設定失敗')
    } finally {
      setBitsSaving(false)
    }
  }

  // --- Redemption handlers ---

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
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <PageHeader title="Events" description="管理頻道事件、自動回應與忠誠點數兌換" />

      <Card>
        <CardHeader>
          <CardTitle>事件列表</CardTitle>
          <CardDescription>設定頻道事件觸發時的自動回應訊息</CardDescription>
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
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHead
                      sortKey="event_type"
                      currentKey={eventSort.sortKey}
                      dir={eventSort.sortDir}
                      onSort={eventSort.toggleSort}
                    >
                      事件名稱
                    </SortableHead>
                    <SortableHead
                      sortKey="type_label"
                      currentKey={eventSort.sortKey}
                      dir={eventSort.sortDir}
                      onSort={eventSort.toggleSort}
                    >
                      類型
                    </SortableHead>
                    <TableHead>訊息模板</TableHead>
                    <SortableHead
                      className="text-right"
                      sortKey="trigger_count"
                      currentKey={eventSort.sortKey}
                      dir={eventSort.sortDir}
                      onSort={eventSort.toggleSort}
                    >
                      觸發次數
                    </SortableHead>
                    <SortableHead
                      className="text-center"
                      sortKey="enabled"
                      currentKey={eventSort.sortKey}
                      dir={eventSort.sortDir}
                      onSort={eventSort.toggleSort}
                    >
                      狀態
                    </SortableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedEvents.map(event => {
                    const locked = isNonPartner && event.event_type === 'subscribe'
                    return (
                      <TableRow key={event.event_type} className={locked ? 'opacity-50' : ''}>
                        <TableCell className="font-medium">
                          <span className="flex items-center gap-1.5">
                            {EVENT_TYPE_NAMES[event.event_type] || event.event_type}
                            {locked && <Icon icon="fa-solid fa-lock" wrapperClassName="size-3.5" />}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge className={EVENT_TYPE_COLORS[event.event_type] || ''}>
                            {EVENT_TYPE_LABELS[event.event_type] || event.event_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-md truncate font-mono text-label">
                          {locked ? (
                            <span className="text-muted-foreground">
                              需要聯盟夥伴或合作夥伴資格
                            </span>
                          ) : (
                            event.message_template
                          )}
                        </TableCell>
                        <TableCell className="text-right">{event.trigger_count}</TableCell>
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

      {/* Redemption Configs */}
      <Card className={isNonPartner ? 'opacity-60' : ''}>
        <CardHeader>
          <CardTitle>忠誠點數兌換</CardTitle>
          <CardDescription>
            {isNonPartner
              ? '此功能需要 Twitch 聯盟夥伴或合作夥伴資格才能使用'
              : '選擇 Twitch 忠誠點數獎勵對應的動作'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {redemptionLoading ? (
            <div className="flex items-center justify-center py-empty">
              <Spinner className="size-8 text-primary" />
            </div>
          ) : isNonPartner ? (
            <div className="flex flex-col items-center justify-center gap-2 py-empty text-muted-foreground">
              <Icon icon="fa-solid fa-lock" wrapperClassName="size-6" />
              <span className="text-sub">成為 Twitch 聯盟夥伴或合作夥伴後即可設定忠誠點數獎勵</span>
            </div>
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
                              <SelectTrigger size="sm" className="w-56">
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

      {/* Bits (Cheer) */}
      <Card>
        <CardHeader>
          <CardTitle>Bits (打賞) 設定</CardTitle>
          <CardDescription>根據 Bits 數量設定分級回應訊息</CardDescription>
          <CardAction>
            <Switch
              checked={bitsConfig?.enabled ?? false}
              onCheckedChange={handleBitsToggle}
              disabled={!bitsConfig}
            />
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-4">
          {bitsTiers.length > 0 && (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-28">最低 Bits</TableHead>
                    <TableHead className="w-28">最高 Bits</TableHead>
                    <TableHead>訊息模板</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {bitsTiers.map((tier, idx) => (
                    <TableRow key={tier.min_bits}>
                      <TableCell>{tier.min_bits}</TableCell>
                      <TableCell>{tier.max_bits ?? '不限'}</TableCell>
                      <TableCell className="font-mono text-sub">{tier.message}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveBitsTier(idx)}
                          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        >
                          <Icon icon="fa-solid fa-xmark" className="text-xs" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {/* Add tier form */}
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label className="text-sub">最低 Bits</Label>
              <Input
                type="number"
                min={1}
                value={newTierMin}
                onChange={e => setNewTierMin(e.target.value)}
                className="w-24"
                placeholder="1"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-sub">最高 Bits</Label>
              <Input
                type="number"
                min={1}
                value={newTierMax}
                onChange={e => setNewTierMax(e.target.value)}
                className="w-24"
                placeholder="不限"
              />
            </div>
            <div className="flex flex-1 flex-col gap-1">
              <Label className="text-sub">
                訊息模板
                <span className="text-muted-foreground ml-1">(可用: $(user), $(amount))</span>
              </Label>
              <Input
                value={newTierMsg}
                onChange={e => setNewTierMsg(e.target.value)}
                placeholder="感謝 $(user) 的 $(amount) bits！"
                className="font-mono"
              />
            </div>
            <Button size="sm" onClick={handleAddBitsTier}>
              新增
            </Button>
          </div>
          <div className="flex justify-end">
            <Button size="sm" onClick={handleSaveBitsTiers} disabled={bitsSaving}>
              {bitsSaving ? '儲存中...' : '儲存分級設定'}
            </Button>
          </div>
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

          <div className="flex flex-col gap-card px-page">
            {/* Message Template */}
            <div className="flex flex-col gap-2">
              <Label>訊息模板</Label>
              <Input
                ref={templateInputRef}
                value={editTemplate}
                onChange={e => setEditTemplate(e.target.value)}
                placeholder="輸入回應訊息..."
                className="font-mono text-sub"
              />

              {/* Available Variables */}
              {editingEvent && TEMPLATE_VARIABLES[editingEvent.event_type] && (
                <VariableInserter
                  variables={TEMPLATE_VARIABLES[editingEvent.event_type]}
                  onInsert={insertVariable}
                />
              )}
            </div>

            {/* Raid: Auto-Shoutout Toggle */}
            {editingEvent?.event_type === 'raid' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <Label>自動 Shoutout</Label>
                  <span className="text-label text-muted-foreground">
                    Raid 時自動執行 /shoutout 展示對方頻道
                  </span>
                </div>
                <Switch
                  checked={(editOptions.auto_shoutout as boolean) ?? true}
                  onCheckedChange={v => setEditOptions(prev => ({ ...prev, auto_shoutout: v }))}
                />
              </div>
            )}

            {/* Enabled Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <Label>啟用</Label>
                <span className="text-label text-muted-foreground">
                  關閉後事件觸發時不會發送訊息
                </span>
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
