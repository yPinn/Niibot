import { useMemo } from 'react'

import { Icon } from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

interface ServiceStatus {
  name: string
  status: 'online' | 'offline'
  uptime?: number
  details?: {
    bot_id?: string
    connected_channels?: number
    service?: string
    db_connected?: boolean
  }
}

export default function SystemStatus() {
  useDocumentTitle('System Status')
  const { twitch, discord, api, lastUpdate, refresh } = useServiceStatus()

  const services = useMemo<ServiceStatus[]>(
    () => [
      {
        name: 'Twitch Bot',
        status: twitch.online ? 'online' : 'offline',
        uptime: twitch.uptime_seconds,
        details: {
          bot_id: twitch.bot_id,
          connected_channels: twitch.connected_channels,
          service: twitch.service,
        },
      },
      {
        name: 'Discord Bot',
        status: discord.online ? 'online' : 'offline',
        uptime: discord.uptime_seconds,
        details: {
          bot_id: discord.bot_id,
          connected_channels: discord.connected_channels,
          service: discord.service,
        },
      },
      {
        name: 'API Server',
        status: api.online ? 'online' : 'offline',
        uptime: api.uptime_seconds,
        details: {
          service: api.service,
          db_connected: api.db_connected,
        },
      },
    ],
    [twitch, discord, api]
  )

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
        return 'text-status-online'
      case 'offline':
        return 'text-status-offline'
    }
  }

  const getStatusIcon = (status: ServiceStatus['status']) => {
    switch (status) {
      case 'online':
        return 'fa-solid fa-circle-check'
      case 'offline':
        return 'fa-solid fa-circle-xmark'
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:gap-card lg:p-page-lg">
      <div className="flex items-center justify-between">
        <h1 className="text-page-title font-bold">系統狀態 (System Status)</h1>
        <div className="flex items-center gap-2 text-sub text-muted-foreground">
          <Icon icon="fa-solid fa-clock" className="w-4 h-4" />
          <span>最後更新：{lastUpdate.toLocaleTimeString()}</span>
          <button
            onClick={refresh}
            className="ml-2 p-1 hover:bg-muted rounded transition-all active:scale-95"
            title="重新整理"
          >
            <Icon icon="fa-solid fa-rotate" className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid gap-section md:grid-cols-2 lg:grid-cols-3">
        {services.map(service => (
          <div key={service.name} className="bg-card border rounded-lg p-6 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-card-title">{service.name}</h3>
              <div className={`flex items-center gap-2 ${getStatusColor(service.status)}`}>
                <Icon icon={getStatusIcon(service.status)} className="w-5 h-5" />
                <span className="text-sm font-medium capitalize">{service.status}</span>
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
                {service.details?.db_connected !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">資料庫連線：</span>
                    <span
                      className={`font-medium ${service.details.db_connected ? 'text-status-online' : 'text-status-offline'}`}
                    >
                      {service.details.db_connected ? '已連線' : '未連線'}
                    </span>
                  </div>
                )}
              </div>
            )}

            {service.status === 'offline' && (
              <div className="text-sub text-muted-foreground">服務目前無法使用</div>
            )}
          </div>
        ))}
      </div>

      <div className="bg-muted/50 border rounded-lg p-4">
        <h3 className="text-card-title font-semibold mb-2 flex items-center gap-2">
          <Icon icon="fa-solid fa-circle-info" className="w-4 h-4" />
          系統資訊
        </h3>
        <div className="text-sub text-muted-foreground space-y-1">
          <p>狀態檢查每 30 秒執行一次</p>
          <p>所有服務皆應保持在線以確保功能完整</p>
        </div>
      </div>
    </main>
  )
}
