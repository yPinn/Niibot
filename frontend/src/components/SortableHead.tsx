import { Icon } from '@/components/primitives'
import { TableHead } from '@/components/ui'
import type { SortState } from '@/hooks/useSortState'

export interface SortableHeadProps<K extends string> {
  sortKey: K
  /** The whole `useSortState` return value — current column, direction, toggle. */
  sort: SortState<K>
  children: React.ReactNode
  className?: string
}

/**
 * A <TableHead> cell with a clickable sort button.
 * Highlights the active column and shows the correct sort-direction arrow.
 */
export function SortableHead<K extends string>({
  sortKey: key,
  sort,
  children,
  className,
}: SortableHeadProps<K>) {
  const active = key === sort.sortKey
  return (
    <TableHead className={className}>
      <button
        type="button"
        className="inline-flex items-center gap-1 cursor-pointer transition-colors hover:text-foreground select-none"
        onClick={() => sort.toggleSort(key)}
      >
        {children}
        <Icon
          icon={
            active
              ? sort.sortDir === 'asc'
                ? 'fa-solid fa-sort-up'
                : 'fa-solid fa-sort-down'
              : 'fa-solid fa-sort'
          }
          className={active ? 'text-foreground' : 'text-muted-foreground/50'}
          wrapperClassName="size-3"
        />
      </button>
    </TableHead>
  )
}
