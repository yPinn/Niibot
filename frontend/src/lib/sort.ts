/** Shared sort utilities — used by Commands, Events, PublicCommands and sub-components. */

export type SortDir = 'asc' | 'desc'

/** Flip an ascending comparison result to match `dir`. */
export function applyDir(cmp: number, dir: SortDir): number {
  return dir === 'desc' ? -cmp : cmp
}

/**
 * Sorts strings so ASCII names (English commands) come before CJK names.
 * A leading '!' prefix is stripped before comparison so command names render
 * consistently whether or not the caller has already appended the prefix.
 */
export function nameSort(a: string, b: string): number {
  const cleanA = a.startsWith('!') ? a.slice(1) : a
  const cleanB = b.startsWith('!') ? b.slice(1) : b
  const aAscii = cleanA.charCodeAt(0) < 128
  const bAscii = cleanB.charCodeAt(0) < 128
  if (aAscii !== bAscii) return aAscii ? -1 : 1
  return cleanA.localeCompare(cleanB, 'zh-TW')
}

/** Canonical role ordering — lower number = lower privilege. */
export const ROLE_ORDER: Record<string, number> = {
  everyone: 0,
  subscriber: 1,
  vip: 2,
  moderator: 3,
  broadcaster: 4,
}
