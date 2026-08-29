export interface CategoryGroup<T> {
  /** Category display label, or null for the trailing "uncategorised" group. */
  label: string | null
  rows: T[]
}

/**
 * Buckets rows by `category_label`, keeping groups in first-appearance order —
 * the commands API returns builtins in the backend `BUILTIN_DEFS` order, which is
 * already the intended category order. Rows with no label collapse into one group
 * placed last. `sortWithin` orders the rows inside each group (the active table
 * sort), leaving the group order itself untouched.
 */
export function groupByCategory<T extends { category_label?: string | null }>(
  rows: T[],
  sortWithin: (a: T, b: T) => number
): CategoryGroup<T>[] {
  const buckets = new Map<string | null, T[]>()
  for (const row of rows) {
    const key = row.category_label ?? null
    const bucket = buckets.get(key)
    if (bucket) bucket.push(row)
    else buckets.set(key, [row])
  }

  // Labelled groups keep first-appearance order; the unlabelled group sorts last.
  const entries = [...buckets.entries()]
  const ordered = [
    ...entries.filter(([label]) => label !== null),
    ...entries.filter(([label]) => label === null),
  ]

  return ordered.map(([label, groupRows]) => ({
    label,
    rows: groupRows.sort(sortWithin),
  }))
}
