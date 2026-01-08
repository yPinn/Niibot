import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type AnalyticsCommandStat,
  type AnalyticsSummary,
  getAnalyticsSummary,
  getTopCommands,
} from '@/api/analytics'
import { type ChannelStats, getChannelStats } from '@/api/stats'
import AnalyticsChart from '@/components/AnalyticsChart'
import StatsCard from '@/components/StatsCard'
import TwitchPlayer from '@/components/TwitchPlayer'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import { useAuth } from '@/contexts/AuthContext'

export default function Dashboard() {
  const { user, isInitialized } = useAuth()
  const [myChannelSubscribed, setMyChannelSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [stats, setStats] = useState<ChannelStats | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null)
  const [topCommands, setTopCommands] = useState<AnalyticsCommandStat[]>([])

  // 防止重複載入
  const hasLoadedRef = useRef(false)

  const fetchMyStatus = useCallback(async () => {
    if (!user) return

    try {
      const response = await fetch('/api/channels/my-status', { credentials: 'include' })
      if (response.ok) {
        const data = await response.json()
        setMyChannelSubscribed(data.subscribed)
      }
    } catch (error) {
      console.error('Failed to fetch my channel status:', error)
    }
  }, [user])

  const fetchStats = useCallback(async () => {
    if (!user) return
    setStatsLoading(true)
    try {
      setStats(await getChannelStats())
    } catch (error) {
      console.error('Failed to fetch stats:', error)
      setStats(null)
    } finally {
      setStatsLoading(false)
    }
  }, [user])

  const fetchAnalytics = useCallback(async () => {
    if (!user) return
    setAnalyticsLoading(true)
    try {
      const [analyticsData, commandsData] = await Promise.all([
        getAnalyticsSummary(30),
        getTopCommands(30, 10),
      ])
      setAnalytics(analyticsData)
      setTopCommands(commandsData)
    } catch (error) {
      console.error('Failed to fetch analytics:', error)
      setAnalytics(null)
      setTopCommands([])
    } finally {
      setAnalyticsLoading(false)
    }
  }, [user])

  // 當 AuthContext 初始化完成且有用戶時，立即載入資料
  useEffect(() => {
    if (!isInitialized || !user || hasLoadedRef.current) return

    hasLoadedRef.current = true

    // 並行載入所有資料
    fetchMyStatus()
    fetchStats()
    fetchAnalytics()
  }, [isInitialized, user, fetchMyStatus, fetchStats, fetchAnalytics])

  const toggleMyChannelSubscription = async () => {
    if (!user) return

    setLoading(true)
    try {
      const response = await fetch('/api/channels/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ channel_id: user.id, enabled: !myChannelSubscribed }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to toggle subscription')
      }

      await fetchMyStatus()
    } catch (error) {
      console.error('Error toggling subscription:', error)
      alert(
        `Failed to toggle subscription: ${error instanceof Error ? error.message : 'Unknown error'}`
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4">
      {user && (
        <div className="flex items-center justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger
              className="flex items-center gap-2 px-4 py-2 rounded-md border bg-card hover:bg-accent transition-colors disabled:opacity-50"
              disabled={loading}
            >
              <div
                className={`h-2 w-2 rounded-full mr-1 ${myChannelSubscribed ? 'bg-green-500' : 'bg-muted-foreground'}`}
              />
              <span className="text-sm font-semibold">
                Niibot {myChannelSubscribed ? 'Online' : 'Offline'}
              </span>
              <Icon icon="fa-solid fa-chevron-down" wrapperClassName="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="w-[var(--radix-dropdown-menu-trigger-width)]"
            >
              <DropdownMenuItem onClick={toggleMyChannelSubscription} disabled={loading}>
                <Icon
                  icon={myChannelSubscribed ? 'fa-solid fa-pause' : 'fa-solid fa-play'}
                  wrapperClassName="mr-2 size-4"
                />
                <span>{myChannelSubscribed ? '停用訂閱' : '啟用訂閱'}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      <AnalyticsChart
        data={
          analytics
            ? {
                totalStreamHours: analytics.total_stream_hours,
                totalSessions: analytics.total_sessions,
                totalCommands: analytics.total_commands,
                totalFollows: analytics.total_follows,
                totalSubs: analytics.total_subs,
                avgSessionDuration: analytics.avg_session_duration,
              }
            : null
        }
        loading={analyticsLoading}
        className="md:col-span-3"
      />

      <div className="grid auto-rows-min gap-4 md:grid-cols-3">
        <div className="bg-muted/50 rounded-xl overflow-hidden aspect-video relative">
          {user?.name ? (
            <TwitchPlayer
              channel="llazypilot"
              height="100%"
              muted={true}
              autoplay={true}
              className="w-full h-full"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-muted-foreground text-sm">Loading player...</div>
            </div>
          )}
        </div>

        <StatsCard
          title="Top Chatters"
          icon="fa-solid fa-comments"
          items={
            stats?.top_chatters.map(chatter => ({
              label: chatter.username,
              value: chatter.message_count,
            })) || []
          }
          loading={statsLoading}
          className="aspect-video"
        />

        <StatsCard
          title="Top Commands"
          icon="fa-solid fa-terminal"
          items={topCommands.map(cmd => ({ label: cmd.command_name, value: cmd.usage_count }))}
          loading={analyticsLoading}
          className="aspect-video"
        />
      </div>
    </main>
  )
}
