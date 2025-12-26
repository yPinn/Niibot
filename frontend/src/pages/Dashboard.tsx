import { useCallback, useEffect, useState } from 'react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import { useAuth } from '@/contexts/AuthContext'

export default function Dashboard() {
  const { user } = useAuth()
  const [myChannelSubscribed, setMyChannelSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)

  // 從 API 獲取當前使用者的頻道訂閱狀態
  const fetchMyStatus = useCallback(async () => {
    if (!user) return

    try {
      const response = await fetch('/api/channels/my-status', {
        credentials: 'include',
      })

      if (response.ok) {
        const data = await response.json()
        setMyChannelSubscribed(data.subscribed)
      } else {
        console.error('Failed to fetch my channel status:', response.status)
      }
    } catch (error) {
      console.error('Failed to fetch my channel status:', error)
    }
  }, [user])

  // 初始化當前使用者的頻道訂閱狀態
  useEffect(() => {
    fetchMyStatus()
  }, [fetchMyStatus])

  // 切換當前使用者的頻道訂閱狀態
  const toggleMyChannelSubscription = async () => {
    if (!user) return

    setLoading(true)
    try {
      const response = await fetch('/api/channels/toggle', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          channel_id: user.id,
          enabled: !myChannelSubscribed,
        }),
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
                className={`h-2 w-2 rounded-full mr-1 ${myChannelSubscribed ? 'bg-green-500' : 'bg-gray-400'}`}
              />
              <span className="text-sm font-medium">
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
      <div className="bg-muted/50 min-h-[100vh] flex-1 rounded-xl md:min-h-min" />
      <div className="grid auto-rows-min gap-4 md:grid-cols-3">
        <div className="bg-muted/50 aspect-video rounded-xl" />
        <div className="bg-muted/50 aspect-video rounded-xl" />
        <div className="bg-muted/50 aspect-video rounded-xl" />
      </div>
    </main>
  )
}
