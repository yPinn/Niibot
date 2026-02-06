import { useCallback, useEffect, useRef, useState } from 'react'

import { getTwitchChannelStatus, toggleTwitchChannel } from '@/api/channels'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuth } from '@/contexts/AuthContext'

export function OnlineDropdown() {
  const { user, isInitialized, botStatus } = useAuth()
  const [myChannelSubscribed, setMyChannelSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)
  const hasLoadedRef = useRef(false)

  const fetchMyStatus = useCallback(async () => {
    if (!user) return
    try {
      const data = await getTwitchChannelStatus()
      if (data) {
        setMyChannelSubscribed(data.subscribed)
      }
    } catch (error) {
      console.error('Failed to fetch my channel status:', error)
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

  if (!user) return null

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div>
          <DropdownMenu>
            <DropdownMenuTrigger
              className="flex items-center gap-2 px-4 py-2 rounded-md border bg-card hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={loading || !botStatus.online}
            >
              <div
                className={`size-2 rounded-full ${
                  !botStatus.online
                    ? 'bg-destructive'
                    : myChannelSubscribed
                      ? 'bg-green-500'
                      : 'bg-yellow-500'
                }`}
              />
              <span className="text-sm font-semibold mx-1 mr-2">Niibot</span>
              <Icon icon="fa-solid fa-chevron-down" wrapperClassName="size-2" />
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="w-[var(--radix-dropdown-menu-trigger-width)]"
            >
              <DropdownMenuItem
                onClick={toggleMyChannelSubscription}
                disabled={loading || !botStatus.online}
              >
                <Icon
                  icon={myChannelSubscribed ? 'fa-solid fa-pause' : 'fa-solid fa-play'}
                  wrapperClassName="mr-2 size-4"
                />
                <span>{myChannelSubscribed ? '停用訂閱' : '啟用訂閱'}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </TooltipTrigger>
      <TooltipContent side="left">
        {!botStatus.online ? 'Bot 離線' : myChannelSubscribed ? '追蹤中' : '沒有追蹤'}
      </TooltipContent>
    </Tooltip>
  )
}
