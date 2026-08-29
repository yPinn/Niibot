import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type EventConfig,
  type EventDefinition,
  getEventCatalog,
  getEventConfigs,
  getRedemptionConfigs,
  getTwitchRewards,
  type RedemptionConfig,
  toggleEventConfig,
  type TwitchReward,
  updateRedemptionConfig,
} from '@/api/events'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'
import { applyDir } from '@/lib/sort'
import { toastApiError } from '@/lib/toast-error'

import { ACTION_TYPE_LABELS } from './constants'
import { EventSheet } from './EventSheet'
import { EventsTable } from './EventsTable'
import { RedemptionsCard } from './RedemptionsCard'
import type { EventSortKey, RedemptionSortKey } from './types'

export default function Events() {
  useDocumentTitle('Events')
  const { isAffiliate } = useAuth()
  const [events, setEvents] = useState<EventConfig[]>([])
  const [catalog, setCatalog] = useState<EventDefinition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editingEvent, setEditingEvent] = useState<EventConfig | null>(null)

  const eventSort = useSortState<EventSortKey>('event_type')
  const redSort = useSortState<RedemptionSortKey>('action_type')

  const [redemptions, setRedemptions] = useState<RedemptionConfig[]>([])
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [rewardsLoading, setRewardsLoading] = useState(true)

  const fetchEvents = useCallback(async () => {
    try {
      setError(null)
      // Both come from the same backend catalog — fail together so the table
      // never renders without the metadata that drives its labels and locks.
      const [configs, defs] = await Promise.all([getEventConfigs(), getEventCatalog()])
      setEvents(configs)
      setCatalog(defs)
    } catch {
      setError('無法載入事件設定')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchRedemptions = useCallback(async () => {
    // Kick off both requests in parallel
    const configsPromise = getRedemptionConfigs()
    const rewardsPromise = isAffiliate
      ? getTwitchRewards().catch(() => [] as TwitchReward[])
      : Promise.resolve([] as TwitchReward[])

    // Configs (own DB) — settle first, reveal table rows immediately
    try {
      setRedemptions(await configsPromise)
    } catch (err) {
      if (import.meta.env.DEV) console.error('Failed to load redemptions:', err)
    } finally {
      setRedemptionLoading(false)
    }

    // Rewards (Twitch API) — settle independently, only affects dropdown cell
    try {
      const rewards = await rewardsPromise
      setTwitchRewards([...rewards].sort((a, b) => a.cost - b.cost))
    } finally {
      setRewardsLoading(false)
    }
  }, [isAffiliate])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchEvents()

    fetchRedemptions()
  }, [fetchEvents, fetchRedemptions])

  const { catalogMap, orderIndex } = useMemo(
    () => ({
      catalogMap: new Map(catalog.map(d => [d.key, d])),
      orderIndex: new Map(catalog.map((d, i) => [d.key, i])),
    }),
    [catalog]
  )

  const { sortKey: eventSortKey, sortDir: eventSortDir } = eventSort
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => {
      let cmp = 0
      switch (eventSortKey) {
        case 'event_type':
          cmp = (orderIndex.get(a.event_type) ?? 99) - (orderIndex.get(b.event_type) ?? 99)
          break
        case 'type_label':
          cmp = (catalogMap.get(a.event_type)?.category_label ?? a.event_type).localeCompare(
            catalogMap.get(b.event_type)?.category_label ?? b.event_type
          )
          break
        case 'trigger_count':
          cmp = (a.trigger_count ?? -1) - (b.trigger_count ?? -1)
          break
        case 'enabled':
          cmp = Number(a.enabled) - Number(b.enabled)
          break
      }
      return applyDir(cmp, eventSortDir)
    })
  }, [events, eventSortKey, eventSortDir, catalogMap, orderIndex])

  const { sortKey: redSortKey, sortDir: redSortDir } = redSort
  const sortedRedemptions = useMemo(() => {
    return [...redemptions]
      .filter(r => r.action_type !== 'niibot_auth')
      .sort((a, b) => {
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
        return applyDir(cmp, redSortDir)
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

  const handleRewardSelect = async (red: RedemptionConfig, rewardTitle: string) => {
    try {
      const updated = await updateRedemptionConfig(red.action_type, {
        reward_name: rewardTitle,
        enabled: red.enabled,
      })
      setRedemptions(prev => prev.map(r => (r.action_type === updated.action_type ? updated : r)))
      toast.success('忠誠點數獎勵已更新')
    } catch (e) {
      toastApiError(e, '更新忠誠點數獎勵失敗')
    }
  }

  return (
    <PageMain>
      <PageHeader title="Events" description="管理頻道事件、自動回應與忠誠點數兌換" />

      <div className="grid grid-cols-1 items-start gap-section xl:grid-cols-[3fr_2fr]">
        <EventsTable
          events={sortedEvents}
          catalog={catalogMap}
          loading={loading}
          error={error}
          sort={eventSort}
          isAffiliate={isAffiliate}
          onToggle={handleToggle}
          onEdit={setEditingEvent}
        />

        <RedemptionsCard
          redemptions={sortedRedemptions}
          twitchRewards={twitchRewards}
          redemptionLoading={redemptionLoading}
          rewardsLoading={rewardsLoading}
          sort={redSort}
          isAffiliate={isAffiliate}
          onToggle={handleRedemptionToggle}
          onRewardSelect={handleRewardSelect}
        />
      </div>

      <EventSheet
        event={editingEvent}
        definition={editingEvent ? catalogMap.get(editingEvent.event_type) : undefined}
        onClose={() => setEditingEvent(null)}
        onSaved={updated => {
          setEvents(prev => prev.map(e => (e.event_type === updated.event_type ? updated : e)))
          setEditingEvent(null)
        }}
      />
    </PageMain>
  )
}
