'use client'

import * as React from 'react'

import { NavMain } from '@/components/nav-main'
import { NavProjects } from '@/components/nav-projects'
import { NavSecondary } from '@/components/nav-secondary'
import { NavUser } from '@/components/nav-user'
import { Icon } from '@/components/ui/icon'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { useAuth } from '@/contexts/AuthContext'

const data = {
  navMain: [
    {
      title: 'Playground',
      url: '#',
      icon: 'fa-solid fa-terminal',
      isActive: true,
      items: [
        {
          title: 'History',
          url: '#',
        },
        {
          title: 'Starred',
          url: '#',
        },
        {
          title: 'Settings',
          url: '#',
        },
      ],
    },
    {
      title: 'Models',
      url: '#',
      icon: 'fa-solid fa-robot',
      items: [
        {
          title: 'Genesis',
          url: '#',
        },
        {
          title: 'Explorer',
          url: '#',
        },
        {
          title: 'Quantum',
          url: '#',
        },
      ],
    },
    {
      title: 'Documentation',
      url: '#',
      icon: 'fa-solid fa-book',
      items: [
        {
          title: 'Introduction',
          url: '#',
        },
        {
          title: 'Get Started',
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
    {
      title: 'Settings',
      url: '#',
      icon: 'fa-solid fa-gear',
      items: [
        {
          title: 'General',
          url: '#',
        },
        {
          title: 'Team',
          url: '#',
        },
        {
          title: 'Billing',
          url: '#',
        },
        {
          title: 'Limits',
          url: '#',
        },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Github',
      url: '#',
      icon: 'fa-brands fa-github',
    },
    {
      title: 'Discord',
      url: 'https://discord.gg/GubS4Xcb7W',
      icon: 'fa-brands fa-discord',
    },
  ],
  projects: [
    {
      name: 'Design Engineering',
      url: '#',
      icon: 'fa-solid fa-border-all',
    },
    {
      name: 'Sales & Marketing',
      url: '#',
      icon: 'fa-solid fa-chart-pie',
    },
    {
      name: 'Travel',
      url: '#',
      icon: 'fa-solid fa-map-location-dot',
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user, isLoading } = useAuth()

  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <a href="/">
                <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <Icon icon="fa-solid fa-terminal" className="size-4" />
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
        <NavMain items={data.navMain} />
        <NavProjects projects={data.projects} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        {isLoading ? (
          <div className="flex items-center justify-center p-4">
            <span className="text-sm text-muted-foreground">Loading...</span>
          </div>
        ) : user ? (
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
