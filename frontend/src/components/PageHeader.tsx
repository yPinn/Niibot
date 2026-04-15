import { SlideUp } from '@/components/ui'
import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  title: string
  description?: string
  className?: string
}

/**
 * Standard page header used at the top of every dashboard page.
 * Renders an <h1> and an optional description paragraph.
 */
export function PageHeader({ title, description, className }: PageHeaderProps) {
  return (
    <SlideUp className={cn(className)}>
      <h1 className="text-page-title font-bold">{title}</h1>
      {description && <p className="text-sub text-muted-foreground">{description}</p>}
    </SlideUp>
  )
}
