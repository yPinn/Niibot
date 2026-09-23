import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface BlockInfoCell {
  label: string
  /** e.g. a binding-status Badge — optional, but every cell reserves the
   * same label-row height whether or not one is present (see below). */
  badge?: ReactNode
  value: ReactNode
  note?: ReactNode
}

interface BlockInfoGridProps {
  cells: BlockInfoCell[]
  className?: string
}

/**
 * The label/badge/value/note cell every live-display block card (check-in,
 * tarot, and whatever gets added next) repeats to describe how it triggers.
 * Centralized so a new block card gets correct alignment by construction
 * instead of re-deriving it: `min-h-5` on the label row matches Badge's own
 * rendered height, so a cell with a status badge next to its label doesn't
 * push its value/note rows out of line with sibling cells that have none.
 */
export function BlockInfoGrid({ cells, className }: BlockInfoGridProps) {
  return (
    <div className={cn('grid min-w-0 gap-section', className)}>
      {cells.map(cell => (
        <div key={cell.label} className="space-y-1">
          <div className="flex min-h-5 flex-wrap items-center gap-element">
            <p className="text-label text-muted-foreground">{cell.label}</p>
            {cell.badge}
          </div>
          <p className="text-content font-semibold">{cell.value}</p>
          {cell.note && <p className="text-label text-muted-foreground">{cell.note}</p>}
        </div>
      ))}
    </div>
  )
}
