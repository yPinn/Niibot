import { useState } from 'react'

import type { SortDir } from '@/lib/sort'

export interface SortState<K extends string> {
  sortKey: K
  sortDir: SortDir
  toggleSort: (key: K) => void
}

/**
 * Manages a single sort column + direction pair.
 * Clicking the current column flips direction; clicking a new column resets to 'asc'.
 *
 * Usage:
 *   const sort = useSortState<'name' | 'cooldown'>('name')
 *   <SortableHead sortKey="name" currentKey={sort.sortKey} dir={sort.sortDir} onSort={sort.toggleSort} />
 */
export function useSortState<K extends string>(initialKey: K): SortState<K> {
  const [sortKey, setSortKey] = useState<K>(initialKey)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const toggleSort = (key: K) => {
    if (key === sortKey) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  return { sortKey, sortDir, toggleSort }
}
