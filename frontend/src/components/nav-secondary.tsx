import * as React from 'react'
import { Link } from 'react-router-dom'

import {
  Icon,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui'

export function NavSecondary({
  items,
  ...props
}: {
  items: {
    title: string
    url: string
    icon: string
    internal?: boolean
  }[]
} & React.ComponentPropsWithoutRef<typeof SidebarGroup>) {
  return (
    <SidebarGroup {...props}>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map(item => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton size="sm" tooltip={item.title} asChild>
                {item.internal ? (
                  <Link to={item.url}>
                    <Icon icon={item.icon} />
                    <span>{item.title}</span>
                  </Link>
                ) : (
                  <a href={item.url} target="_blank" rel="noopener noreferrer">
                    <Icon icon={item.icon} />
                    <span>{item.title}</span>
                  </a>
                )}
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
