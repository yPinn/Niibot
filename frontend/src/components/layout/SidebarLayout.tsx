import { Fragment, Suspense } from 'react'
import { Outlet } from 'react-router-dom'

import { AppSidebar } from '@/components/layout/app-sidebar'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { OnlineDropdown } from '@/components/OnlineDropdown'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
  Separator,
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useBreadcrumbs } from '@/hooks/useBreadcrumbs'

export default function SidebarLayout() {
  const { user } = useAuth()
  const breadcrumbs = useBreadcrumbs()

  return (
    <SidebarProvider className="h-svh! min-h-0!">
      <AppSidebar />
      <SidebarInset className="min-h-0!">
        <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b px-page transition-[width,height] duration-slow ease-default group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
            {breadcrumbs.length > 0 && (
              <Breadcrumb>
                <BreadcrumbList>
                  {breadcrumbs.map((item, index) => (
                    <Fragment key={item.href ?? item.label}>
                      {index > 0 && <BreadcrumbSeparator className="hidden md:block" />}
                      <BreadcrumbItem
                        className={index < breadcrumbs.length - 1 ? 'hidden md:block' : ''}
                      >
                        {index === breadcrumbs.length - 1 ? (
                          <BreadcrumbPage>{item.label}</BreadcrumbPage>
                        ) : (
                          <BreadcrumbLink href={item.href}>{item.label}</BreadcrumbLink>
                        )}
                      </BreadcrumbItem>
                    </Fragment>
                  ))}
                </BreadcrumbList>
              </Breadcrumb>
            )}
          </div>
          {user && <OnlineDropdown />}
        </header>
        {/*
         * Suspense sits here, not around <Routes>, so a lazy page chunk loading
         * on navigation swaps only the content area — the sidebar shell (and its
         * expand/collapse state) never unmounts.
         */}
        <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
          <Suspense
            fallback={
              <div className="flex flex-1 items-center justify-center">
                <LoadingSpinner />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
