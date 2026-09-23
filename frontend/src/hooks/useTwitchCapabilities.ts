import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  getTwitchCapabilities,
  type TwitchCapability,
  type TwitchCapabilityKey,
  type TwitchCapabilitySnapshot,
} from '@/api/botAccounts'
import { useAuth } from '@/contexts/AuthContext'

interface TwitchCapabilitiesState {
  snapshot: TwitchCapabilitySnapshot | null
  loading: boolean
  error: boolean
  capability: (key: TwitchCapabilityKey) => TwitchCapability | null
  isAvailable: (key: TwitchCapabilityKey) => boolean
  refresh: () => Promise<void>
}

export function useTwitchCapabilities(): TwitchCapabilitiesState {
  const { user, isInitialized } = useAuth()
  const [result, setResult] = useState<{
    channelId: string
    snapshot: TwitchCapabilitySnapshot | null
    error: boolean
  } | null>(null)

  const load = useCallback(
    async (forceRefresh = false) => {
      if (!isInitialized || !user) return
      try {
        const snapshot = await getTwitchCapabilities(user.id, { forceRefresh })
        setResult({ channelId: user.id, snapshot, error: false })
      } catch {
        setResult({ channelId: user.id, snapshot: null, error: true })
      }
    },
    [isInitialized, user]
  )

  useEffect(() => {
    if (!isInitialized || !user) return
    let cancelled = false
    const channelId = user.id
    void getTwitchCapabilities(channelId)
      .then(snapshot => {
        if (!cancelled) setResult({ channelId, snapshot, error: false })
      })
      .catch(() => {
        if (!cancelled) setResult({ channelId, snapshot: null, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [isInitialized, user])

  const currentResult = result?.channelId === user?.id ? result : null
  const snapshot = currentResult?.snapshot ?? null
  const loading = Boolean(isInitialized && user && currentResult === null)
  const error = currentResult?.error ?? false

  const byKey = useMemo(
    () => new Map(snapshot?.capabilities.map(item => [item.key, item]) ?? []),
    [snapshot]
  )
  const capability = useCallback((key: TwitchCapabilityKey) => byKey.get(key) ?? null, [byKey])
  const isAvailable = useCallback(
    (key: TwitchCapabilityKey) => byKey.get(key)?.available ?? false,
    [byKey]
  )
  const refresh = useCallback(() => load(true), [load])

  return { snapshot, loading, error, capability, isAvailable, refresh }
}
