import { TableCell, TableRow } from '@/components/ui'

export interface TableGroupHeaderProps {
  label: string
  /** Optional row count shown next to the label. */
  count?: number
  /** Must match the table's column count so the header spans the full width. */
  colSpan: number
}

/**
 * A full-width label row that introduces a group of related rows in a data table.
 * Not interactive — overrides the base row hover.
 */
export function TableGroupHeader({ label, count, colSpan }: TableGroupHeaderProps) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell
        colSpan={colSpan}
        className="bg-muted/50 py-1.5 text-label font-medium text-muted-foreground select-none"
      >
        {label}
        {count !== undefined && <span className="ml-1.5 text-muted-foreground/60">{count}</span>}
      </TableCell>
    </TableRow>
  )
}
