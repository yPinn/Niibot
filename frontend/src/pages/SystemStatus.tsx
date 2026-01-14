import { useCallback, useEffect, useRef, useState } from 'react'

import { type BotStatus, getDiscordBotStatus, getTwitchBotStatus } from '@/api/bots'
import { Icon } from '@/components/ui/icon'

interface ServiceStatus {
  name: string
  status: 'online' | 'offline' | 'loading'
  uptime?: number
  details?: {
    bot_id?: string
    connected_channels?: number
    service?: string
  }
}

export default function SystemStatus() {
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: 'Twitch Bot', status: 'loading' },
    { name: 'Discord Bot', status: 'loading' },
    { name: 'API Server', status: 'loading' },
  ])
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())

  // 使用 useRef 追蹤組件是否仍處於掛載狀態，避免在卸載後執行 setState
  const isMounted = useRef(true)

  const fetchAllStatus = useCallback(async () => {
    try {
      // 使用 Promise.all 並對單個請求進行 catch，確保一個服務失敗不會導致全部卡住
      const [twitchStatus, discordStatus] = await Promise.all([
        getTwitchBotStatus().catch(() => ({ online: false }) as BotStatus),
        getDiscordBotStatus().catch(() => ({ online: false }) as BotStatus),
      ])

      let apiStatus: BotStatus = { online: false }
      try {
        const response = await fetch('/api/health', { credentials: 'include' })
        apiStatus = { online: response.ok }
      } catch {
        apiStatus = { online: false }
      }

      // 如果組件已經卸載，則不更新狀態
      if (!isMounted.current) return

      setServices([
        {
          name: 'Twitch Bot',
          status: twitchStatus.online ? 'online' : 'offline',
          uptime: twitchStatus.uptime_seconds,
          details: {
            bot_id: twitchStatus.bot_id,
            connected_channels: twitchStatus.connected_channels,
            service: twitchStatus.service,
          },
        },
        {
          name: 'Discord Bot',
          status: discordStatus.online ? 'online' : 'offline',
          uptime: discordStatus.uptime_seconds,
          details: {
            bot_id: discordStatus.bot_id,
            connected_channels: discordStatus.connected_channels,
            service: discordStatus.service,
          },
        },
        {
          name: 'API Server',
          status: apiStatus.online ? 'online' : 'offline',
        },
      ])

      setLastUpdate(new Date())
    } catch (error) {
      console.error('無法獲取系統狀態:', error)
    }
  }, [])

  useEffect(() => {
    isMounted.current = true

    // 解決關鍵：將初始化邏輯封裝在非同步函式中呼叫，明確區分同步渲染與非同步副作用
    const initialize = async () => {
      await fetchAllStatus()
    }

    initialize()

    const interval = setInterval(fetchAllStatus, 30000)

    return () => {
      isMounted.current = false
      clearInterval(interval)
    }
  }, [fetchAllStatus])

  const formatUptime = (seconds?: number) => {
    if (!seconds) return 'N/A'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  const getStatusColor = (status: ServiceStatus['status']) => {
    switch (status) {
      case 'online':
        return 'text-green-500'
      case 'offline':
        return 'text-red-500'
      case 'loading':
        return 'text-yellow-500'
    }
  }

  const getStatusIcon = (status: ServiceStatus['status']) => {
    switch (status) {
      case 'online':
        return 'fa-solid fa-circle-check'
      case 'offline':
        return 'fa-solid fa-circle-xmark'
      case 'loading':
        return 'fa-solid fa-spinner fa-spin'
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold md:text-2xl">系統狀態 (System Status)</h1>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon icon="fa-solid fa-clock" className="w-4 h-4" />
          <span>最後更新：{lastUpdate.toLocaleTimeString()}</span>
          <button
            onClick={fetchAllStatus}
            className="ml-2 p-1 hover:bg-muted rounded transition-all active:scale-95"
            title="重新整理"
          >
            <Icon icon="fa-solid fa-rotate" className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {services.map(service => (
          <div key={service.name} className="bg-card border rounded-lg p-6 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-lg">{service.name}</h3>
              <div className={`flex items-center gap-2 ${getStatusColor(service.status)}`}>
                <Icon icon={getStatusIcon(service.status)} className="w-5 h-5" />
                <span className="text-sm font-medium capitalize">
                  {service.status === 'loading' ? '載入中' : service.status}
                </span>
              </div>
            </div>

            {service.status === 'online' && (
              <div className="space-y-2 text-sm">
                {service.uptime !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">運行時間：</span>
                    <span className="font-medium">{formatUptime(service.uptime)}</span>
                  </div>
                )}
                {service.details?.bot_id && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">機器人 ID：</span>
                    <span className="font-mono text-xs">{service.details.bot_id}</span>
                  </div>
                )}
                {service.details?.connected_channels !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">已連接頻道：</span>
                    <span className="font-medium">{service.details.connected_channels}</span>
                  </div>
                )}
              </div>
            )}

            {service.status === 'offline' && (
              <div className="text-sm text-muted-foreground">服務目前無法使用</div>
            )}
          </div>
        ))}
      </div>

      <div className="bg-muted/50 border rounded-lg p-4">
        <h3 className="font-semibold mb-2 flex items-center gap-2">
          <Icon icon="fa-solid fa-circle-info" className="w-4 h-4" />
          系統資訊
        </h3>
        <div className="text-sm text-muted-foreground space-y-1">
          <p>狀態檢查每 30 秒執行一次</p>
          <p>所有服務皆應保持在線以確保功能完整</p>
        </div>
      </div>
    </main>
  )
}
