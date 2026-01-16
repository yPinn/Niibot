'use client'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/ui/icon'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { useBot } from '@/contexts/BotContext'

export function BotSwitcher() {
  const { activeBot, activeBotInfo, setActiveBot, bots } = useBot()

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
                <Icon icon={activeBotInfo.icon} className="size-4" wrapperClassName="" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{activeBotInfo.name}</span>
                <span className="truncate text-xs">{activeBotInfo.description}</span>
              </div>
              <Icon icon="fa-solid fa-chevron-up-down" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            align="start"
            side="bottom"
            sideOffset={4}
          >
            {bots.map(bot => (
              <DropdownMenuItem
                key={bot.id}
                onClick={() => setActiveBot(bot.id)}
                className="gap-2 p-2"
              >
                <div className="flex size-6 items-center justify-center rounded-sm border">
                  <Icon icon={bot.icon} className="size-4 shrink-0" wrapperClassName="" />
                </div>
                <div className="flex flex-col">
                  <span className="font-medium">{bot.name}</span>
                  <span className="text-xs text-muted-foreground">{bot.description}</span>
                </div>
                {activeBot === bot.id && (
                  <Icon
                    icon="fa-solid fa-check"
                    className="ml-auto size-4 text-primary"
                    wrapperClassName=""
                  />
                )}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
