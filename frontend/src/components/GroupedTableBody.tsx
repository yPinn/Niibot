import { Fragment } from 'react'

import { TableGroupHeader } from '@/components/TableGroupHeader'
import { TableBody } from '@/components/ui'
import type { CategoryGroup } from '@/lib/groupByCategory'

export interface GroupedTableBodyProps<T> {
  groups: CategoryGroup<T>[]
  /** Table column count — the group-header row spans all of them. */
  colSpan: number
  /** Renders one data row; must set its own `key` on the returned `<TableRow>`. */
  renderRow: (row: T) => React.ReactNode
}

/**
 * A `<TableBody>` that renders `groupByCategory` output: a `<TableGroupHeader>`
 * before each labelled group, then its rows. The trailing unlabelled group (if
 * any) renders its rows with no header. Replaces the `groups.map` + `<Fragment>`
 * scaffold that BuiltinTab and PublicCommands both copied.
 */
export function GroupedTableBody<T>({ groups, colSpan, renderRow }: GroupedTableBodyProps<T>) {
  return (
    <TableBody>
      {groups.map(group => (
        <Fragment key={group.label ?? '_uncategorised'}>
          {group.label && (
            <TableGroupHeader label={group.label} count={group.rows.length} colSpan={colSpan} />
          )}
          {group.rows.map(renderRow)}
        </Fragment>
      ))}
    </TableBody>
  )
}
