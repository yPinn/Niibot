'use client'

import { useMemo, useState } from 'react'

import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Icon,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui'

interface Channel {
  id: string
  name: string
  display_name: string
  avatar: string
  is_live: boolean
  viewer_count?: number
  game_name?: string
}

type SortType = 'default' | 'alphabet' | 'viewers'

export function NavChannels({ channels }: { channels: Channel[] }) {
  const [sortType, setSortType] = useState<SortType>('default')

  const sortedChannels = useMemo(() => {
    return [...channels].sort((a, b) => {
      // 預設：直播中的在前面，然後按字母排序
      if (sortType === 'default') {
        if (a.is_live !== b.is_live) {
          return a.is_live ? -1 : 1
        }
        return a.name.localeCompare(b.name)
      }

      // 字母排序：直播中的在前面，然後按字母排序
      if (sortType === 'alphabet') {
        if (a.is_live !== b.is_live) {
          return a.is_live ? -1 : 1
        }
        return a.name.localeCompare(b.name)
      }

      // 觀眾人數：直播中的在前面，然後按觀眾數排序
      if (sortType === 'viewers') {
        if (a.is_live !== b.is_live) {
          return a.is_live ? -1 : 1
        }
        if (a.is_live && b.is_live) {
          return (b.viewer_count || 0) - (a.viewer_count || 0)
        }
        return a.name.localeCompare(b.name)
      }

      return 0
    })
  }, [channels, sortType])

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <div className="flex items-center justify-between">
        <SidebarGroupLabel>Channels</SidebarGroupLabel>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex h-7 w-7 mr-0.5 items-center justify-center rounded-md hover:bg-sidebar-accent">
              <Icon
                icon="fa-solid fa-arrow-up-arrow-down"
                wrapperClassName="size-3"
                className="text-muted-foreground"
              />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem
              onClick={() => setSortType('alphabet')}
              className={sortType === 'alphabet' || sortType === 'default' ? 'bg-accent' : ''}
            >
              <Icon icon="fa-solid fa-font" wrapperClassName="mr-2 size-4" />
              <span>字母排序</span>
              {(sortType === 'alphabet' || sortType === 'default') && (
                <Icon icon="fa-solid fa-check" wrapperClassName="ml-auto size-4" />
              )}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setSortType('viewers')}
              className={sortType === 'viewers' ? 'bg-accent' : ''}
            >
              <Icon icon="fa-solid fa-users" wrapperClassName="mr-2 size-4" />
              <span>觀眾人數</span>
              {sortType === 'viewers' && (
                <Icon icon="fa-solid fa-check" wrapperClassName="ml-auto size-4" />
              )}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <SidebarMenu>
        {sortedChannels.length === 0 && (
          <SidebarMenuItem>
            <div className="px-2 py-1.5 text-sm text-muted-foreground">No channels found</div>
          </SidebarMenuItem>
        )}
        {sortedChannels.map(channel => (
          <SidebarMenuItem key={channel.id}>
            <SidebarMenuButton
              asChild
              className={channel.is_live ? 'h-auto py-1.5 items-start' : ''}
            >
              <a
                href={`https://twitch.tv/${channel.name}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <div className="relative shrink-0 mt-0.5">
                  <Avatar
                    className={channel.is_live ? 'size-6 rounded-full' : 'size-5 rounded-full'}
                  >
                    <AvatarImage src={channel.avatar} alt={channel.display_name} />
                    <AvatarFallback className="rounded-full text-[8px]">
                      {channel.display_name.substring(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  {channel.is_live && (
                    <div className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-sidebar" />
                  )}
                </div>
                {channel.is_live ? (
                  <div className="flex flex-1 min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-medium truncate leading-none">
                      {channel.display_name}
                    </span>
                    {channel.game_name && (
                      <span className="text-[11px] text-muted-foreground truncate leading-none">
                        {channel.game_name}
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="flex-1 truncate">{channel.display_name}</span>
                )}
                <div
                  className={`flex items-center gap-1.5 shrink-0 ml-auto${channel.is_live ? ' mt-0.5' : ''}`}
                >
                  {channel.is_live && channel.viewer_count !== undefined && (
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {channel.viewer_count}
                    </span>
                  )}
                  <div
                    className={`h-2 w-2 rounded-full ${channel.is_live ? 'bg-red-500 animate-pulse' : 'bg-gray-400'}`}
                  />
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}
