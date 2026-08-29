import { EmptyState, type EmptyStateProps } from '@/components/primitives'
import { TableCell, TableRow } from '@/components/ui'

export type TableEmptyRowProps = EmptyStateProps & { colSpan: number }

/**
 * The `<TableRow><TableCell colSpan><EmptyState/></TableCell></TableRow>` block that
 * every data table renders when it has no rows. `colSpan` must match the table's
 * column count; remaining props go straight to `EmptyState`.
 */
export function TableEmptyRow({ colSpan, ...emptyState }: TableEmptyRowProps) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan}>
        <EmptyState {...emptyState} />
      </TableCell>
    </TableRow>
  )
}
