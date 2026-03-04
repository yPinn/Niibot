import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
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
  // refresh is exposed in context for on-demand calls; uses a ref so components
  // always call the latest version without stale closures.
  const refreshRef = useRef<() => Promise<void>>(async () => {})

  const refresh = useCallback(async () => {
    return refreshRef.current()
  }, [])

  useEffect(() => {
    if (!user) return

    // Local flag scoped to this effect invocation — immune to the shared-ref
    // race where a new effect re-arms isMounted before the old fetch resolves.
    let mounted = true

    const fetchStatus = async () => {
      const [t, d, a] = await Promise.all([
        getTwitchBotStatus().catch(() => ({ online: false }) as BotStatus),
        getDiscordBotStatus().catch(() => ({ online: false }) as BotStatus),
        getApiServerStatus().catch(() => ({ online: false }) as ApiServerStatus),
      ])
      if (!mounted) return
      setTwitch(t)
      setDiscord(d)
      setApi(a)
      setLastUpdate(new Date())
    }

    refreshRef.current = fetchStatus

    // 避免在 effect body 內同步呼叫 setState — 透過 setTimeout 延遲首次 fetch
    const initialTimeout = setTimeout(fetchStatus, 0)
    const interval = setInterval(fetchStatus, POLL_INTERVAL)
    return () => {
      mounted = false
      clearTimeout(initialTimeout)
      clearInterval(interval)
    }
  }, [user])

  // --- DB 連線狀態 toast 通知 ---
  const prevDbConnected = useRef<boolean | undefined>(undefined)

  useEffect(() => {
    if (!api.online) return

    const prev = prevDbConnected.current
    prevDbConnected.current = api.db_connected

    // 跳過首次取得狀態
    if (prev === undefined) return

    if (api.db_connected === false) {
      // Re-assert on every poll: if toast was dismissed (user click / route change),
      // it will reappear at the next 30s cycle while the DB remains disconnected.
      toast.warning('服務暫時中斷', {
        id: 'db-status',
        duration: Infinity,
        description: '無法連線至資料庫，頁面資料暫時無法載入',
      })
    } else if (api.db_connected === true && prev === false) {
      toast.success('服務已恢復正常', { id: 'db-status', duration: 4000, description: '' })
    }
  }, [api])

  const contextValue = useMemo(
    () => ({ twitch, discord, api, lastUpdate, refresh }),
    [twitch, discord, api, lastUpdate, refresh]
  )

  return (
    <ServiceStatusContext.Provider value={contextValue}>{children}</ServiceStatusContext.Provider>
  )
}

export function useServiceStatus() {
  return useContext(ServiceStatusContext)
}
