import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { cn } from '@/lib/utils'

import { Icon } from './Icon'

interface EmptyStateProps extends Omit<React.ComponentProps<'div'>, 'title'> {
  icon: string
  title: React.ReactNode
  description?: React.ReactNode
}

export function EmptyState({ icon, title, description, className, ...rest }: EmptyStateProps) {
  return (
    <Empty className={cn('border-none', className)} {...rest}>
      <EmptyHeader>
        <EmptyMedia>
          <Icon icon={icon} wrapperClassName="size-20 opacity-25" className="text-[5rem]" />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description && <EmptyDescription>{description}</EmptyDescription>}
      </EmptyHeader>
    </Empty>
  )
}
