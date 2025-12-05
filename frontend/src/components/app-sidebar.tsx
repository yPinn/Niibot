'use client'

import * as React from 'react'

import { getCurrentUser, type User } from '@/api/user'
import { NavMain } from '@/components/nav-main'
import { NavUser } from '@/components/nav-user'
import { TeamSwitcher } from '@/components/team-switcher'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'

// This is sample data.
const data = {
  teams: [
    {
      name: 'Twitch',
      logo: 'fa-brands fa-twitch',
    },
    {
      name: 'Discord',
      logo: 'fa-brands fa-discord',
    },
  ],
  navMain: [
    {
      title: 'Information',
      url: '#',
      icon: 'fa-solid fa-home',
      isActive: true,
      items: [
        {
          title: 'Dashboard',
          url: '/dashboard',
        },
        {
          title: 'Get Started',
          url: '#',
        },
      ],
    },
    {
      title: 'Commands',
      url: '#',
      icon: 'fa-solid fa-terminal',
      items: [
        {
          title: 'List',
          url: '#',
        },
        {
          title: 'Timer',
          url: '#',
        },
      ],
    },
    {
      title: 'Analytics',
      url: '#',
      icon: 'fa-solid fa-chart-line',
      items: [
        {
          title: 'Leaderboard',
          url: '#',
        },
      ],
    },
    {
      title: 'Documentation',
      url: '#',
      icon: 'fa-solid fa-book-open',
      items: [
        {
          title: 'Introduction',
          url: '#',
        },
        {
          title: 'Tutorials',
          url: '#',
        },
        {
          title: 'Changelog',
          url: '#',
        },
      ],
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const [user, setUser] = React.useState<User | null>(null)

  React.useEffect(() => {
    // 獲取使用者資訊
    getCurrentUser().then(userData => {
      if (userData) {
        setUser(userData)
      }
    })
  }, [])

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <TeamSwitcher teams={data.teams} />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
      </SidebarContent>
      <SidebarFooter>
        {user ? (
          <NavUser user={user} />
        ) : (
          <div className="flex items-center justify-center p-4">
            <span className="text-muted-foreground text-sm">Loading...</span>
          </div>
        )}
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
