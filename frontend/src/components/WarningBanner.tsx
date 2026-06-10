import * as React from 'react'

import { Icon } from '@/components/primitives'
import { cn } from '@/lib/utils'

export function WarningBanner({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-xl border border-status-warning/30 bg-status-warning/5 px-page py-3',
        className
      )}
    >
      <Icon
        icon="fa-solid fa-triangle-exclamation"
        size="sm"
        wrapperClassName="mt-0.5 shrink-0 text-status-warning"
      />
      <p className="text-sub leading-relaxed text-status-warning">{children}</p>
    </div>
  )
}
