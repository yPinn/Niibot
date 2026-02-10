import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

import {
  type ApiServerStatus,
  type BotStatus,
  getApiServerStatus,
  getDiscordBotStatus,
  getTwitchBotStatus,
} from '@/api/bots'

import { useAuth } from './AuthContext'

const POLL_INTERVAL = 30_000 // 30s — 全站統一刷新週期

interface ServiceStatusState {
  twitch: BotStatus
  discord: BotStatus
  api: ApiServerStatus
  lastUpdate: Date
  refresh: () => Promise<void>
}

const defaultStatus: ServiceStatusState = {
  twitch: { online: false },
  discord: { online: false },
  api: { online: false },
  lastUpdate: new Date(),
  refresh: async () => {},
}

const ServiceStatusContext = createContext<ServiceStatusState>(defaultStatus)

export function ServiceStatusProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [twitch, setTwitch] = useState<BotStatus>({ online: false })
  const [discord, setDiscord] = useState<BotStatus>({ online: false })
  const [api, setApi] = useState<ApiServerStatus>({ online: false })
  const [lastUpdate, setLastUpdate] = useState(new Date())
  const isMounted = useRef(true)

  const refresh = useCallback(async () => {
    const [t, d, a] = await Promise.all([
      getTwitchBotStatus().catch(() => ({ online: false }) as BotStatus),
      getDiscordBotStatus().catch(() => ({ online: false }) as BotStatus),
      getApiServerStatus().catch(() => ({ online: false }) as ApiServerStatus),
    ])
    if (!isMounted.current) return
    setTwitch(t)
    setDiscord(d)
    setApi(a)
    setLastUpdate(new Date())
  }, [])

  useEffect(() => {
    isMounted.current = true
    if (!user) return

    // 避免在 effect body 內同步呼叫 setState — 透過 setTimeout 延遲首次 fetch
    const initialTimeout = setTimeout(refresh, 0)
    const interval = setInterval(refresh, POLL_INTERVAL)
    return () => {
      isMounted.current = false
      clearTimeout(initialTimeout)
      clearInterval(interval)
    }
  }, [user, refresh])

  return (
    <ServiceStatusContext.Provider value={{ twitch, discord, api, lastUpdate, refresh }}>
      {children}
    </ServiceStatusContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useServiceStatus() {
  return useContext(ServiceStatusContext)
}
