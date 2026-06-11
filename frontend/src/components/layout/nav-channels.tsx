'use client'

import { useMemo, useState } from 'react'

import { type Channel } from '@/api/channels'
import { Icon } from '@/components/primitives'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui'

type SortType = 'alphabet' | 'viewers'

export function NavChannels({ channels }: { channels: Channel[] }) {
  const [sortType, setSortType] = useState<SortType>('viewers')

  const sortedChannels = useMemo(() => {
    return [...channels].sort((a, b) => {
      // Live channels always first
      if (a.is_live !== b.is_live) return a.is_live ? -1 : 1

      if (sortType === 'viewers') {
        if (a.is_live && b.is_live) {
          return (b.viewer_count || 0) - (a.viewer_count || 0)
        }
      }

      return a.name.localeCompare(b.name)
    })
  }, [channels, sortType])

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <div className="flex items-center justify-between">
        <SidebarGroupLabel>Channels</SidebarGroupLabel>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex h-7 w-7 mr-0.5 items-center justify-center rounded-md hover:bg-sidebar-accent select-none">
              <Icon
                icon="fa-solid fa-arrow-up-arrow-down"
                wrapperClassName="size-3"
                className="text-muted-foreground"
              />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
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
            <DropdownMenuItem
              onClick={() => setSortType('alphabet')}
              className={sortType === 'alphabet' ? 'bg-accent' : ''}
            >
              <Icon icon="fa-solid fa-font" wrapperClassName="mr-2 size-4" />
              <span>字母排序</span>
              {sortType === 'alphabet' && (
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
        <TooltipProvider delayDuration={400}>
          {sortedChannels.map(channel => (
            <SidebarMenuItem key={channel.id}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <SidebarMenuButton
                    asChild
                    className={channel.is_live ? 'h-auto py-1.5 items-start' : ''}
                  >
                    <a
                      href={`https://twitch.tv/${channel.name}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <div className="relative shrink-0">
                        <Avatar
                          className={
                            channel.is_live ? 'size-6 rounded-full' : 'size-5 rounded-full'
                          }
                        >
                          <AvatarImage src={channel.avatar} alt={channel.display_name} />
                          <AvatarFallback className="rounded-full text-[8px]">
                            {channel.display_name.substring(0, 2).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        {channel.is_live && (
                          <div className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-status-live ring-2 ring-sidebar" />
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
                      <div className="flex items-center gap-1.5 shrink-0 ml-auto self-center">
                        {channel.is_live && channel.viewer_count !== undefined && (
                          <span className="text-xs tabular-nums text-muted-foreground">
                            {channel.viewer_count}
                          </span>
                        )}
                        <div
                          className={`h-2 w-2 rounded-full ${channel.is_live ? 'bg-status-live animate-pulse' : 'bg-muted-foreground'}`}
                        />
                      </div>
                    </a>
                  </SidebarMenuButton>
                </TooltipTrigger>
                {channel.is_live && channel.title && (
                  <TooltipContent side="right" className="max-w-56">
                    {channel.title}
                  </TooltipContent>
                )}
              </Tooltip>
            </SidebarMenuItem>
          ))}
        </TooltipProvider>
      </SidebarMenu>
    </SidebarGroup>
  )
}
