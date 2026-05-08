export const SORT_COLS = [
  { key: 'messages', label: '留言', icon: 'fa-solid fa-comment', natural: 'desc' },
  { key: 'watch', label: '時長', icon: 'fa-solid fa-clock', natural: 'desc' },
  { key: 'score', label: '活躍度', icon: 'fa-solid fa-fire', natural: 'desc' },
] as const

export type SortKey = (typeof SORT_COLS)[number]['key']
