'use client'

import * as React from 'react'

import { NavChannels } from '@/components/nav-channels'
import { NavMain } from '@/components/nav-main'
import { NavSecondary } from '@/components/nav-secondary'
import { NavUser } from '@/components/nav-user'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { navigationData } from '@/config/navigation'
import { useAuth } from '@/contexts/AuthContext'

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user, channels } = useAuth()

  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <a href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-full overflow-hidden">
                  <img
                    src="/images/Avatar.png"
                    alt="Niibot"
                    className="h-full w-full object-cover"
                  />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">Niibot</span>
                  <span className="truncate text-xs">Twitch Bot</span>
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navigationData.navMain} />
        <NavChannels channels={channels} />
        <NavSecondary items={navigationData.navSecondary} className="mt-auto" />
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
