import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Icon } from '@/components/ui/icon'
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@/components/ui/sidebar'

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
  const [openItems, setOpenItems] = useState<Set<string>>(new Set())

  // 檢查該選單項目是否包含當前路由
  const isItemActive = (item: (typeof items)[0]) => {
    return item.items?.some(subItem => location.pathname === subItem.url) ?? false
  }

  // 路由變化時自動展開對應的選單
  useEffect(() => {
    const activeItem = items.find(item => isItemActive(item))
    if (activeItem) {
      setOpenItems(prev => {
        const next = new Set(prev)
        next.add(activeItem.title)
        return next
      })
    }
  }, [location.pathname])

  // 切換選單展開/收起
  const toggleItem = (title: string) => {
    setOpenItems(prev => {
      const next = new Set(prev)
      if (next.has(title)) {
        next.delete(title)
      } else {
        next.add(title)
      }
      return next
    })
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Console</SidebarGroupLabel>
      <SidebarMenu>
        {items.map(item => (
          <Collapsible
            key={item.title}
            asChild
            open={openItems.has(item.title)}
            onOpenChange={() => toggleItem(item.title)}
          >
            <SidebarMenuItem className="group/collapsible">
              <CollapsibleTrigger asChild>
                <SidebarMenuButton tooltip={item.title}>
                  <Icon icon={item.icon} />
                  <span>{item.title}</span>
                  {item.items?.length ? (
                    <div className="ml-auto size-4 transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90">
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
                          <a href={subItem.url}>
                            <span>{subItem.title}</span>
                          </a>
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
