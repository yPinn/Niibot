import { type ReactNode } from 'react'

import { SlideUp } from '@/components/primitives'
import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  title: string
  description?: string
  className?: string
  children?: ReactNode
}

/**
 * Standard page header used at the top of every dashboard page.
 * Renders an <h1>, an optional description paragraph, and an optional right-side action slot.
 */
export function PageHeader({ title, description, className, children }: PageHeaderProps) {
  return (
    <SlideUp className={cn('flex items-start justify-between gap-4', className)}>
      <div>
        <h1 className="text-page-title font-bold">{title}</h1>
        {description && <p className="text-sub text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="flex items-center gap-2 shrink-0 pt-0.5">{children}</div>}
    </SlideUp>
  )
}
