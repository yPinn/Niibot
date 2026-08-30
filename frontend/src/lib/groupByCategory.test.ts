import { describe, expect, it } from 'vitest'

import { groupByCategory } from '@/lib/groupByCategory'

interface Row {
  name: string
  category_label?: string | null
}

const byName = (a: Row, b: Row) => a.name.localeCompare(b.name)

describe('groupByCategory', () => {
  it('keeps groups in first-appearance order', () => {
    const rows: Row[] = [
      { name: 'a', category_label: '通用' },
      { name: 'b', category_label: '娛樂' },
      { name: 'c', category_label: '通用' },
    ]
    const groups = groupByCategory(rows, byName)
    expect(groups.map(g => g.label)).toEqual(['通用', '娛樂'])
    expect(groups[0].rows.map(r => r.name)).toEqual(['a', 'c'])
  })

  it('sorts within each group without reordering groups', () => {
    const rows: Row[] = [
      { name: 'z', category_label: '通用' },
      { name: 'a', category_label: '通用' },
      { name: 'm', category_label: '娛樂' },
    ]
    const groups = groupByCategory(rows, byName)
    expect(groups.map(g => g.label)).toEqual(['通用', '娛樂'])
    expect(groups[0].rows.map(r => r.name)).toEqual(['a', 'z'])
  })

  it('collapses null / undefined labels into one trailing group', () => {
    const rows: Row[] = [
      { name: 'x', category_label: null },
      { name: 'a', category_label: '通用' },
      { name: 'y' },
    ]
    const groups = groupByCategory(rows, byName)
    expect(groups.map(g => g.label)).toEqual(['通用', null])
    expect(groups[1].rows.map(r => r.name)).toEqual(['x', 'y'])
  })

  it('returns an empty array for empty input', () => {
    expect(groupByCategory([], byName)).toEqual([])
  })

  it('does not mutate the input array', () => {
    const rows: Row[] = [
      { name: 'b', category_label: '通用' },
      { name: 'a', category_label: '通用' },
    ]
    groupByCategory(rows, byName)
    expect(rows.map(r => r.name)).toEqual(['b', 'a'])
  })
})
