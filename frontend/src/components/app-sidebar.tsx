'use client'

import * as React from 'react'

import { BotSwitcher } from '@/components/bot-switcher'
import { NavChannels } from '@/components/nav-channels'
import { NavMain } from '@/components/nav-main'
import { NavSecondary } from '@/components/nav-secondary'
import { NavUser } from '@/components/nav-user'
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader } from '@/components/ui'
import { discordNavigationData, navigationData } from '@/config/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useBot } from '@/contexts/BotContext'

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user, channels } = useAuth()
  const { activeBot } = useBot()

  // 根據當前選擇的 Bot 顯示不同的導航
  const currentNavData = activeBot === 'discord' ? discordNavigationData : navigationData

  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <BotSwitcher />
      </SidebarHeader>
      <SidebarContent className="overflow-hidden">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <NavMain items={currentNavData.navMain} />
          {activeBot === 'twitch' && <NavChannels channels={channels} />}
        </div>
        <NavSecondary items={currentNavData.navSecondary} />
      </SidebarContent>
      <SidebarFooter>
        {user ? (
          <NavUser user={user} />
        ) : (
          <div className="flex items-center justify-center p-4">
            <a href="/login" className="text-sm text-primary hover:underline">
              Login
            </a>
          </div>
        )}
      </SidebarFooter>
    </Sidebar>
  )
}
