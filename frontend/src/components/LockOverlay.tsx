import type { ReactNode } from 'react'

import { Icon } from '@/components/primitives'
import { cn } from '@/lib/utils'

interface LockOverlayProps {
  icon: string
  title: string
  description: ReactNode
  /** When true, uses sticky h-svh wrapper to centre in viewport (for full-page locks). */
  fullPage?: boolean
  className?: string
}

export function LockOverlay({
  icon,
  title,
  description,
  fullPage = false,
  className,
}: LockOverlayProps) {
  const card = (
    <div className="flex w-full max-w-xs flex-col items-center gap-section rounded-xl border bg-card p-card text-center shadow-lg">
      <div className="flex size-14 items-center justify-center rounded-full bg-muted">
        <Icon icon={icon} wrapperClassName="size-6" className="text-xl text-muted-foreground" />
      </div>
      <div className="flex flex-col gap-element">
        <p className="text-page-title font-semibold">{title}</p>
        <p className="text-sub leading-relaxed text-muted-foreground">{description}</p>
      </div>
    </div>
  )

  return (
    <div className={cn('absolute inset-0 z-modal bg-background/80 backdrop-blur-sm', className)}>
      {fullPage ? (
        <div className="sticky top-0 flex h-svh items-center justify-center p-page">{card}</div>
      ) : (
        <div className="flex h-full items-center justify-center p-page">{card}</div>
      )}
    </div>
  )
}
