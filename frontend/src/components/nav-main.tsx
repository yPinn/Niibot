import { useCallback, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'

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
  const [manuallyOpenedItems, setManuallyOpenedItems] = useState<Set<string>>(new Set())
  const [manuallyClosedItems, setManuallyClosedItems] = useState<Set<string>>(new Set())

  const isItemActive = useCallback(
    (item: (typeof items)[0]) => {
      return item.items?.some(subItem => location.pathname === subItem.url) ?? false
    },
    [location.pathname]
  )

  const openItems = useMemo(() => {
    const open = new Set<string>()
    items.forEach(item => {
      const active = isItemActive(item)
      const manuallyOpened = manuallyOpenedItems.has(item.title)
      const manuallyClosed = manuallyClosedItems.has(item.title)

      if (manuallyOpened) {
        open.add(item.title)
      } else if (manuallyClosed) {
        // closed
      } else if (active) {
        open.add(item.title)
      }
    })
    return open
  }, [items, isItemActive, manuallyOpenedItems, manuallyClosedItems])

  const toggleItem = (title: string, isOpen: boolean) => {
    if (isOpen) {
      setManuallyOpenedItems(prev => {
        const next = new Set(prev)
        next.add(title)
        return next
      })
      setManuallyClosedItems(prev => {
        const next = new Set(prev)
        next.delete(title)
        return next
      })
    } else {
      setManuallyClosedItems(prev => {
        const next = new Set(prev)
        next.add(title)
        return next
      })
      setManuallyOpenedItems(prev => {
        const next = new Set(prev)
        next.delete(title)
        return next
      })
    }
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
            onOpenChange={isOpen => toggleItem(item.title, isOpen)}
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
