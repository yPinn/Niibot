import { Outlet } from 'react-router-dom'

import { AppSidebar } from '@/components/app-sidebar'
import { OnlineDropdown } from '@/components/OnlineDropdown'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { useAuth } from '@/contexts/AuthContext'
import { useBreadcrumbs } from '@/hooks/useBreadcrumbs'

export default function SidebarLayout() {
  const { user } = useAuth()
  const breadcrumbs = useBreadcrumbs()

  return (
    <SidebarProvider className="!h-svh !min-h-0">
      <AppSidebar />
      <SidebarInset className="!min-h-0">
        <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b px-4 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
            {breadcrumbs.length > 0 && (
              <Breadcrumb>
                <BreadcrumbList>
                  {breadcrumbs.map((item, index) => (
                    <div key={index} className="flex items-center gap-2">
                      {index > 0 && <BreadcrumbSeparator className="hidden md:block" />}
                      <BreadcrumbItem className={index === 0 ? 'hidden md:block' : ''}>
                        {index === breadcrumbs.length - 1 ? (
                          <BreadcrumbPage>{item.label}</BreadcrumbPage>
                        ) : (
                          <BreadcrumbLink href={item.href}>{item.label}</BreadcrumbLink>
                        )}
                      </BreadcrumbItem>
                    </div>
                  ))}
                </BreadcrumbList>
              </Breadcrumb>
            )}
          </div>
          {user && <OnlineDropdown />}
        </header>
        <div className="flex-1 min-h-0 overflow-auto">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
