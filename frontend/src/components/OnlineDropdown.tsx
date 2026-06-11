import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { getBotModStatus, getTwitchChannelStatus, toggleTwitchChannel } from '@/api/channels'
import { Icon } from '@/components/primitives'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useGrantMod } from '@/hooks/useGrantMod'

export function OnlineDropdown() {
  const { user, isInitialized } = useAuth()
  const { twitch: botStatus } = useServiceStatus()
  const [myChannelSubscribed, setMyChannelSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [isMod, setIsMod] = useState<boolean | null>(null)
  const hasLoadedRef = useRef(false)
  const { granting: grantingMod, grantMod: handleGrantMod } = useGrantMod(() => setIsMod(true))

  const fetchChannelStatus = useCallback(async () => {
    if (!user) return
    try {
      const data = await getTwitchChannelStatus()
      if (data) setMyChannelSubscribed(data.subscribed)
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to fetch channel status:', error)
    }
  }, [user])

  const fetchMyStatus = useCallback(async () => {
    if (!user) return
    try {
      const [channelData, modRes] = await Promise.all([getTwitchChannelStatus(), getBotModStatus()])
      if (channelData) setMyChannelSubscribed(channelData.subscribed)
      if (modRes.ok) setIsMod(modRes.data.is_moderator)
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to fetch status:', error)
    }
  }, [user])

  useEffect(() => {
    if (!isInitialized || !user || hasLoadedRef.current) return
    hasLoadedRef.current = true
    fetchMyStatus()
  }, [isInitialized, user, fetchMyStatus])

  const toggleMyChannelSubscription = async () => {
    if (!user) return
    setLoading(true)
    try {
      await toggleTwitchChannel(user.id, !myChannelSubscribed)
      await fetchChannelStatus()
    } catch (error) {
      if (import.meta.env.DEV) console.error('Error toggling subscription:', error)
      toast.error('無法切換訂閱狀態', {
        description: '請稍後再試',
      })
    } finally {
      setLoading(false)
    }
  }

  if (!user) return null

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger
            className="flex items-center gap-2 px-4 py-2 rounded-md border bg-card hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={loading || !botStatus.online}
          >
            <div
              className={`size-2 rounded-full ${
                !botStatus.online
                  ? 'bg-destructive'
                  : myChannelSubscribed
                    ? 'bg-status-online'
                    : 'bg-status-loading'
              }`}
            />
            <span className="text-sub font-semibold mx-1 mr-2">Niibot</span>
            <Icon icon="fa-solid fa-chevron-down" wrapperClassName="size-2" />
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="left">
          {!botStatus.online ? 'Bot 離線' : myChannelSubscribed ? '追蹤中' : '沒有追蹤'}
        </TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-(--radix-dropdown-menu-trigger-width)">
        <DropdownMenuItem
          onClick={handleGrantMod}
          disabled={grantingMod || isMod === true || !botStatus.online}
        >
          <Icon
            icon={grantingMod ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-sword'}
            wrapperClassName={isMod ? 'text-status-success' : ''}
          />
          {grantingMod ? '授予中…' : isMod ? '已是管理員' : '授予 Mod'}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={toggleMyChannelSubscription}
          disabled={loading || !botStatus.online}
        >
          <Icon icon={myChannelSubscribed ? 'fa-solid fa-pause' : 'fa-solid fa-play'} />
          {myChannelSubscribed ? '停用訂閱' : '啟用訂閱'}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
