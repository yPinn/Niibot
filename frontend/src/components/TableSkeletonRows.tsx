import { Skeleton } from '@/components/ui'
import { cn } from '@/lib/utils'

interface TableSkeletonRowsProps {
  count?: number
  /**
   * Per-column width classes (e.g. `['w-[20%]', 'flex-1', 'w-[8%]']`). When set,
   * rows are column-shaped to line up with the real table; omit for plain
   * full-width bars. Use column mode only for single-line-cell tables — a table
   * with multi-line cells should keep a bespoke skeleton.
   */
  columns?: string[]
}

/** The loading placeholder every sortable-table card renders while fetching. */
export function TableSkeletonRows({ count = 5, columns }: TableSkeletonRowsProps) {
  if (!columns) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: count }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    )
  }
  return (
    <div className="flex flex-col">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-section px-2 py-3">
          {columns.map((w, j) => (
            <Skeleton key={j} className={cn('h-4', w)} />
          ))}
        </div>
      ))}
    </div>
  )
}
