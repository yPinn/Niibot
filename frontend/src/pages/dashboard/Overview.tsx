import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function Dashboard() {
  useDocumentTitle('Dashboard')
  const { user, isInitialized, channels } = useAuth()

  const defaultChannel = useMemo(() => {
    if (channels.length === 0) return 'niibot_'
    const live = channels.filter(ch => ch.is_live)
    if (live.length === 0) return channels[0].name
    return live.reduce((a, b) => ((a.viewer_count ?? 0) >= (b.viewer_count ?? 0) ? a : b)).name
  }, [channels])
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [stats, setStats] = useState<ChannelStats | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null)
  const [topCommands, setTopCommands] = useState<AnalyticsCommandStat[]>([])
  const hasLoadedRef = useRef(false)

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

  useEffect(() => {
    if (!isInitialized || !user || hasLoadedRef.current) return
    hasLoadedRef.current = true
    fetchStats()
    fetchAnalytics()
  }, [isInitialized, user, fetchStats, fetchAnalytics])

  // Refetch stats when a channel goes offline (new session data available)
  const prevChannelsRef = useRef(channels)
  useEffect(() => {
    const prev = prevChannelsRef.current
    prevChannelsRef.current = channels

    // Skip on initial load
    if (!hasLoadedRef.current) return

    const wentOffline = prev.some(p => p.is_live && !channels.find(c => c.id === p.id)?.is_live)
    if (wentOffline) {
      fetchStats()
      fetchAnalytics()
    }
  }, [channels, fetchStats, fetchAnalytics])

  return (
    <main
      className={`h-full grid grid-rows-[1fr_auto] min-h-0 overflow-hidden transition-all duration-200 p-page gap-section`}
    >
      <AnalyticsChart data={analytics} loading={analyticsLoading} className="min-h-0" />

      <div className={`grid grid-cols-1 md:grid-cols-3 gap-section`}>
        <div className="aspect-video bg-muted/50 rounded-xl overflow-hidden relative">
          {user?.name ? (
            <TwitchPlayer
              channel={defaultChannel}
              height="100%"
              muted={true}
              autoplay={true}
              className="w-full h-full"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-muted-foreground text-sub">Loading player...</div>
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
          className="aspect-video overflow-hidden"
        />

        <StatsCard
          title="Top Commands"
          icon="fa-solid fa-terminal"
          items={topCommands.map(cmd => ({ label: cmd.command_name, value: cmd.usage_count }))}
          loading={analyticsLoading}
          className="aspect-video overflow-hidden"
        />
      </div>
    </main>
  )
}
