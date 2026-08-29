import { Table } from '@/components/ui'
import { cn } from '@/lib/utils'

export interface TableShellProps {
  children: React.ReactNode
  /** `table-fixed` layout (column widths enforced by `<th>`). Default true. */
  fixed?: boolean
  className?: string
}

/**
 * The `overflow-x-auto rounded-md border` frame every sortable-table card renders
 * inside, wrapping a `<Table>`. Extracted verbatim from the pages that copy-pasted
 * it.
 */
export function TableShell({ children, fixed = true, className }: TableShellProps) {
  return (
    <div className={cn('overflow-x-auto rounded-md border', className)}>
      <Table className={fixed ? 'table-fixed' : undefined}>{children}</Table>
    </div>
  )
}
