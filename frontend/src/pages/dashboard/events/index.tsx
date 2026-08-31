import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  type EventConfig,
  type EventDefinition,
  getEventCatalog,
  getEventConfigs,
  toggleEventConfig,
} from '@/api/events'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'
import { applyDir } from '@/lib/sort'

import { EventSheet } from './EventSheet'
import { EventsTable } from './EventsTable'
import type { EventSortKey } from './types'

export default function Events() {
  useDocumentTitle('Events')
  const { isAffiliate } = useAuth()
  const [events, setEvents] = useState<EventConfig[]>([])
  const [catalog, setCatalog] = useState<EventDefinition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editingEvent, setEditingEvent] = useState<EventConfig | null>(null)

  const eventSort = useSortState<EventSortKey>('event_type')

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

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchEvents()
  }, [fetchEvents])

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

  const { toggle: handleToggle } = useOptimisticToggle<EventConfig>({
    setState: setEvents,
    getId: e => e.event_type,
    toggleFn: (e, enabled) => toggleEventConfig(e.event_type, enabled).then(() => {}),
    messages: { on: '事件已啟用', off: '事件已停用', error: '切換事件狀態失敗' },
  })

  return (
    <PageMain>
      <PageHeader title="Events" description="管理 Twitch EventSub 事件與自動回應模板。" />

      <div className="grid grid-cols-1 items-start gap-section">
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
