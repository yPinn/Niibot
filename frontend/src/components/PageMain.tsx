import * as React from 'react'

import { cn } from '@/lib/utils'

export function PageMain({ className, ...props }: React.ComponentProps<'main'>) {
  return (
    <main
      className={cn(
        'flex flex-1 flex-col gap-section p-page lg:p-page-lg min-h-0 overflow-y-auto',
        className
      )}
      {...props}
    />
  )
}
