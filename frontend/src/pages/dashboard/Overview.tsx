import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { type AnalyticsSummary, getAnalyticsSummary } from '@/api/analytics'
import { type ChannelStats, getChannelStats } from '@/api/stats'
import AnalyticsChart from '@/components/AnalyticsChart'
import StatsCard from '@/components/StatsCard'
import TwitchPlayer from '@/components/TwitchPlayer'
import { Skeleton, SlideUp, Stagger, StaggerItem } from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function Dashboard() {
  useDocumentTitle('Dashboard')
  const { user, isInitialized, channels } = useAuth()

  const defaultChannel = useMemo(() => {
    const fallback = user?.name ?? 'niibot_' // dev fallback — user is always set in production
    const live = channels.filter(ch => ch.is_live)
    if (live.length === 0) return fallback
    return live.reduce((a, b) => ((a.viewer_count ?? 0) >= (b.viewer_count ?? 0) ? a : b)).name
  }, [channels, user?.name])
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [stats, setStats] = useState<ChannelStats | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null)
  const loadedForUserRef = useRef<string | null>(null)

  const fetchStats = useCallback(async () => {
    if (!user) return
    setStatsLoading(true)
    try {
      setStats(await getChannelStats())
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to fetch stats:', error)
      setStats(null)
    } finally {
      setStatsLoading(false)
    }
  }, [user])

  const fetchAnalytics = useCallback(async () => {
    if (!user) return
    setAnalyticsLoading(true)
    try {
      setAnalytics(await getAnalyticsSummary(30))
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to fetch analytics:', error)
      setAnalytics(null)
    } finally {
      setAnalyticsLoading(false)
    }
  }, [user])

  useEffect(() => {
    if (!isInitialized || !user) return
    if (loadedForUserRef.current === user.id) return
    loadedForUserRef.current = user.id
    fetchStats()
    fetchAnalytics()
  }, [isInitialized, user, fetchStats, fetchAnalytics])

  // Refetch stats when a channel goes offline (new session data available)
  const prevChannelsRef = useRef(channels)
  useEffect(() => {
    const prev = prevChannelsRef.current
    prevChannelsRef.current = channels

    // Skip on initial load
    if (loadedForUserRef.current === null) return

    const wentOffline = prev.some(p => p.is_live && !channels.find(c => c.id === p.id)?.is_live)
    if (wentOffline) {
      fetchStats()
      fetchAnalytics()
    }
  }, [channels, fetchStats, fetchAnalytics])

  return (
    <main className="flex flex-col flex-1 min-h-0 gap-section p-page overflow-y-auto lg:p-page-lg transition-all duration-slow ease-default">
      <SlideUp inView>
        <AnalyticsChart data={analytics} loading={analyticsLoading} days={30} />
      </SlideUp>

      <Stagger inView className="grid grid-cols-1 lg:grid-cols-3 gap-section">
        <StaggerItem className="aspect-video bg-muted/50 rounded-xl overflow-hidden relative">
          {user?.name ? (
            <TwitchPlayer
              channel={defaultChannel}
              height="100%"
              muted={true}
              autoplay={true}
              className="w-full h-full"
            />
          ) : (
            <Skeleton className="absolute inset-0 rounded-xl" />
          )}
        </StaggerItem>

        <StaggerItem>
          <StatsCard
            title="Top Chatters"
            icon="fa-solid fa-comments"
            items={
              stats?.top_chatters.map(chatter => ({
                label: chatter.display_name || chatter.username,
                value: chatter.message_count,
              })) || []
            }
            loading={statsLoading}
            className="aspect-video overflow-hidden"
          />
        </StaggerItem>

        <StaggerItem>
          <StatsCard
            title="Top Commands"
            icon="fa-solid fa-terminal"
            items={stats?.top_commands.map(cmd => ({ label: cmd.name, value: cmd.count })) || []}
            loading={statsLoading}
            className="aspect-video overflow-hidden"
          />
        </StaggerItem>
      </Stagger>
    </main>
  )
}
