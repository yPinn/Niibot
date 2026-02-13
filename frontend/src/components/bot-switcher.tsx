'use client'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui'
import { useBot } from '@/contexts/BotContext'

export function BotSwitcher() {
  const { activeBot, activeBotInfo, setActiveBot, bots, canSwitchBot } = useBot()
  const { isMobile } = useSidebar()

  if (!canSwitchBot) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" className="cursor-default">
            <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
              <i className={`${activeBotInfo.icon} text-base`} />
            </div>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-semibold">{activeBotInfo.name}</span>
              <span className="truncate text-xs">{activeBotInfo.description}</span>
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <i className={`${activeBotInfo.icon} text-base`} />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{activeBotInfo.name}</span>
                <span className="truncate text-xs">{activeBotInfo.description}</span>
              </div>
              <i className="fa-solid fa-chevrons-up-down ml-auto" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            align="start"
            side={isMobile ? 'bottom' : 'right'}
            sideOffset={4}
          >
            {bots.map(bot => (
              <DropdownMenuItem
                key={bot.id}
                onClick={() => setActiveBot(bot.id)}
                className="gap-2 p-2"
              >
                <div className="flex size-6 items-center justify-center rounded-sm border">
                  <i className={`${bot.icon} text-sm`} />
                </div>
                {bot.description}
                {activeBot === bot.id && <i className="fa-solid fa-check ml-auto" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
