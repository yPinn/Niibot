import { useEffect, useRef, useState } from 'react'

import { getBotModStatus } from '@/api/channels'
import { getCommandConfigs } from '@/api/commands'
import { getEventConfigs } from '@/api/events'
import { getTimerConfigs } from '@/api/timers'
import { getTriggerConfigs } from '@/api/triggers'
import { useAuth } from '@/contexts/AuthContext'
import type { OnboardingStatus } from '@/lib/onboarding-status'

const EMPTY_STATUS: OnboardingStatus = {
  modDone: null,
  commandsDone: null,
  eventsDone: null,
  timersDone: null,
}

export function useOnboardingStatus(): { loading: boolean; status: OnboardingStatus } {
  const { user, isInitialized, isAffiliate } = useAuth()
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<OnboardingStatus>(EMPTY_STATUS)
  const loadedForRef = useRef<string | null>(null)

  useEffect(() => {
    if (!isInitialized || !user) return
    if (loadedForRef.current === user.id) return
    loadedForRef.current = user.id

    let cancelled = false
    setLoading(true)

    async function load() {
      const [modResult, commandsResult, triggersResult, eventsResult, timersResult] =
        await Promise.allSettled([
          getBotModStatus(),
          getCommandConfigs(),
          getTriggerConfigs(),
          isAffiliate ? getEventConfigs() : Promise.resolve(null),
          getTimerConfigs(),
        ])

      const modDone =
        modResult.status === 'fulfilled' && modResult.value.ok
          ? modResult.value.data.is_moderator
          : null

      const commandsDone =
        commandsResult.status === 'fulfilled' && triggersResult.status === 'fulfilled'
          ? commandsResult.value.some(c => c.command_type === 'custom') ||
            triggersResult.value.length > 0
          : null

      const eventsDone = !isAffiliate
        ? null
        : eventsResult.status === 'fulfilled' && eventsResult.value !== null
          ? eventsResult.value.some(e => e.enabled)
          : null

      const timersDone =
        timersResult.status === 'fulfilled' ? timersResult.value.some(t => !t.builtin) : null

      if (!cancelled) {
        setStatus({ modDone, commandsDone, eventsDone, timersDone })
        setLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [isInitialized, user, isAffiliate])

  return { loading, status }
}
