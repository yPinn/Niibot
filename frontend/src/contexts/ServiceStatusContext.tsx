import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

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

  // --- 系統狀態 toast 通知 ---
  const prevApi = useRef<ApiServerStatus | null>(null)

  useEffect(() => {
    // 跳過初次載入（避免頁面刷新時跳通知）
    if (prevApi.current === null) {
      prevApi.current = api
      return
    }

    const prev = prevApi.current
    prevApi.current = api

    // API 離線 / 恢復
    if (!api.online && prev.online) {
      toast.warning('API 服務離線', { id: 'api-status', duration: Infinity })
    } else if (api.online && !prev.online) {
      toast.success('API 服務已恢復', { id: 'api-status', duration: 4000 })
    }

    // DB 斷線 / 恢復（僅在 API 在線時偵測）
    if (api.online && api.db_connected === false && prev.db_connected !== false) {
      toast.warning('資料庫連線中斷', { id: 'db-status', duration: Infinity })
    } else if (api.online && api.db_connected === true && prev.db_connected === false) {
      toast.success('資料庫已恢復連線', { id: 'db-status', duration: 4000 })
    }
  }, [api])

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
