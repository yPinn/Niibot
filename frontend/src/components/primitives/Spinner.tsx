import { cn } from '@/lib/utils'

import { Icon } from './Icon'

function Spinner({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <Icon
      icon="fa-solid fa-spinner"
      wrapperClassName={cn('size-4 animate-spin', className)}
      role="status"
      aria-label="Loading"
      {...props}
    />
  )
}

export { Spinner }
