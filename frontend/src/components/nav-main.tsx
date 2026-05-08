import { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Icon,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from '@/components/ui'

export function NavMain({
  items,
}: {
  items: {
    title: string
    url: string
    icon: string
    isActive?: boolean
    items?: {
      title: string
      url: string
    }[]
  }[]
}) {
  const location = useLocation()
  const { state: sidebarState, toggleSidebar } = useSidebar()

  // 將 pathname 一起存入，換頁時自動回退至 active route，無需 useEffect
  const [openItem, setOpenItem] = useState<{ title: string; pathname: string } | null>(null)

  const activeTitle = useMemo(
    () => items.find(item => item.items?.some(sub => location.pathname === sub.url))?.title ?? null,
    [items, location.pathname]
  )

  const isOpen = (title: string) => {
    if (openItem !== null && openItem.pathname === location.pathname) {
      return openItem.title === title
    }
    return activeTitle === title
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Console</SidebarGroupLabel>
      <SidebarMenu>
        {items.map(item => (
          <Collapsible
            key={item.title}
            asChild
            open={isOpen(item.title)}
            onOpenChange={shouldOpen => {
              if (sidebarState === 'collapsed') {
                // icon mode：展開 sidebar 並指定要打開的選單
                toggleSidebar()
                setOpenItem({ title: item.title, pathname: location.pathname })
              } else {
                // accordion：同時只能開一項
                setOpenItem(shouldOpen ? { title: item.title, pathname: location.pathname } : null)
              }
            }}
          >
            <SidebarMenuItem className="group/collapsible">
              <CollapsibleTrigger asChild>
                <SidebarMenuButton tooltip={item.title}>
                  <Icon icon={item.icon} />
                  <span>{item.title}</span>
                  {item.items?.length ? (
                    <div className="ml-auto size-4 transition-transform duration-slow ease-default group-data-[state=open]/collapsible:rotate-90">
                      <Icon icon="fa-solid fa-chevron-right" wrapperClassName="size-4" />
                    </div>
                  ) : null}
                </SidebarMenuButton>
              </CollapsibleTrigger>
              {item.items?.length ? (
                <CollapsibleContent>
                  <SidebarMenuSub>
                    {item.items?.map(subItem => (
                      <SidebarMenuSubItem key={subItem.title}>
                        <SidebarMenuSubButton asChild isActive={location.pathname === subItem.url}>
                          <Link to={subItem.url}>
                            <span>{subItem.title}</span>
                          </Link>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    ))}
                  </SidebarMenuSub>
                </CollapsibleContent>
              ) : null}
            </SidebarMenuItem>
          </Collapsible>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}
