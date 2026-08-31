import * as React from 'react'
import { Link } from 'react-router-dom'

import { BotSwitcher } from '@/components/layout/bot-switcher'
import { NavChannels } from '@/components/layout/nav-channels'
import { NavMain } from '@/components/layout/nav-main'
import { NavSecondary } from '@/components/layout/nav-secondary'
import { NavUser } from '@/components/layout/nav-user'
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader } from '@/components/ui'
import { discordNavigationData, navigationData } from '@/config/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useBot } from '@/contexts/BotContext'

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user, channels } = useAuth()
  const { activeBot } = useBot()

  const currentNavData = activeBot === 'discord' ? discordNavigationData : navigationData

  const navMain = currentNavData.navMain.filter(item => !item.ownerOnly || user?.is_owner)

  return (
    <Sidebar variant="inset" collapsible="icon" {...props}>
      <SidebarHeader>
        <BotSwitcher />
      </SidebarHeader>
      <SidebarContent className="overflow-hidden">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <NavMain items={navMain} />
          {activeBot === 'twitch' && <NavChannels channels={channels} />}
        </div>
        <NavSecondary items={currentNavData.navSecondary} />
      </SidebarContent>
      <SidebarFooter>
        {user ? (
          <NavUser user={user} showWorkspaces={activeBot === 'twitch'} />
        ) : (
          <div className="flex items-center justify-center p-4">
            <Link to="/login" className="text-sm text-primary hover:underline">
              Login
            </Link>
          </div>
        )}
      </SidebarFooter>
    </Sidebar>
  )
}
