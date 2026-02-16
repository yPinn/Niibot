import { useCallback, useEffect, useRef, useState } from 'react'

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
import {
  Badge,
  Button,
  Card,
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
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

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
  follow: '新追隨者',
  subscribe: '訂閱感謝',
  raid: 'Raid 歡迎',
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  vip: 'VIP 授予',
  first: '搶第一公告',
  niibot_auth: 'Niibot 授權',
}

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
  const templateInputRef = useRef<HTMLInputElement>(null)

  // Redemption state
  const [redemptions, setRedemptions] = useState<RedemptionConfig[]>([])
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [isNonPartner, setIsNonPartner] = useState(false)

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

  // --- Redemption handlers ---

  const handleRedemptionToggle = async (red: RedemptionConfig) => {
    const newEnabled = !red.enabled
    setRedemptions(prev =>
      prev.map(r => (r.action_type === red.action_type ? { ...r, enabled: newEnabled } : r))
    )
    try {
      await updateRedemptionConfig(red.action_type, {
        reward_name: red.reward_name,
        enabled: newEnabled,
      })
    } catch {
      setRedemptions(prev =>
        prev.map(r => (r.action_type === red.action_type ? { ...r, enabled: red.enabled } : r))
      )
    }
  }

  const handleRewardSelect = async (red: RedemptionConfig, rewardTitle: string) => {
    try {
      const updated = await updateRedemptionConfig(red.action_type, {
        reward_name: rewardTitle,
        enabled: red.enabled,
      })
      setRedemptions(prev => prev.map(r => (r.action_type === updated.action_type ? updated : r)))
    } catch {
      // Silently fail
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
      <div>
        <h1 className="text-page-title font-bold">Events</h1>
        <p className="text-sub text-muted-foreground">管理頻道事件、自動回應與忠誠點數兌換</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>事件列表</CardTitle>
          <CardDescription>設定頻道事件觸發時的自動回應訊息</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-empty text-muted-foreground">
              載入中...
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-empty text-destructive">
              {error}
            </div>
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
                  {events.map(event => {
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
                        <TableCell className="max-w-md truncate font-mono text-xs">
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
            <div className="flex items-center justify-center py-empty text-muted-foreground">
              載入中...
            </div>
          ) : isNonPartner ? (
            <div className="flex flex-col items-center justify-center gap-2 py-empty text-muted-foreground">
              <Icon icon="fa-solid fa-lock" wrapperClassName="size-6" />
              <span className="text-sm">成為 Twitch 聯盟夥伴或合作夥伴後即可設定忠誠點數獎勵</span>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>動作</TableHead>
                    <TableHead>獎勵名稱</TableHead>
                    <TableHead className="text-center">狀態</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {redemptions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-center text-muted-foreground">
                        尚無兌換設定
                      </TableCell>
                    </TableRow>
                  ) : (
                    redemptions.map(red => (
                      <TableRow key={red.action_type}>
                        <TableCell className="font-medium">
                          {ACTION_TYPE_LABELS[red.action_type] || red.action_type}
                        </TableCell>
                        <TableCell>
                          {twitchRewards.length === 0 ? (
                            <span className="text-sm text-muted-foreground">
                              請先在 Twitch 建立自訂獎勵
                            </span>
                          ) : (
                            <Select
                              value={red.reward_name}
                              onValueChange={v => handleRewardSelect(red, v)}
                            >
                              <SelectTrigger size="sm" className="w-56">
                                <SelectValue placeholder="選擇獎勵..." />
                              </SelectTrigger>
                              <SelectContent>
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
                className="font-mono text-sm"
              />

              {/* Available Variables */}
              {editingEvent && TEMPLATE_VARIABLES[editingEvent.event_type] && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-label text-muted-foreground">可用變數（點擊插入）</span>
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
