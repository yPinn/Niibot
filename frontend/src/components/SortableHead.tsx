import { Icon, TableHead } from '@/components/ui'
import type { SortDir } from '@/lib/sort'

export interface SortableHeadProps<K extends string> {
  sortKey: K
  currentKey: K
  dir: SortDir
  onSort: (key: K) => void
  children: React.ReactNode
  className?: string
}

/**
 * A <TableHead> cell with a clickable sort button.
 * Highlights the active column and shows the correct sort-direction arrow.
 */
export function SortableHead<K extends string>({
  sortKey: key,
  currentKey,
  dir,
  onSort,
  children,
  className,
}: SortableHeadProps<K>) {
  const active = key === currentKey
  return (
    <TableHead className={className}>
      <button
        type="button"
        className="inline-flex items-center gap-1 cursor-pointer transition-colors hover:text-foreground select-none"
        onClick={() => onSort(key)}
      >
        {children}
        <Icon
          icon={
            active
              ? dir === 'asc'
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
