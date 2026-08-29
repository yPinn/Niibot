/**
 * Twitch Plus Program thresholds and progress math.
 *
 * Plus Points: Tier 1 sub = 1, Tier 2 = 2, Tier 3 = 6 (gifted / Prime subs earn
 * none). 100 points sustained for 3 months unlocks a 60/40 revenue split, 300
 * points a 70/30 split. The backend does the point tally; this is display math.
 */
export const PLUS_TIER1_POINTS = 100
export const PLUS_TIER2_POINTS = 300

export type PlusSplit = '50/50' | '60/40' | '70/30'

export interface PlusProgress {
  split: PlusSplit
  /** Points needed to reach the next split, or null at the top. */
  nextThreshold: number | null
  /** Points still needed for `nextThreshold` (0 at the top). */
  remaining: number
  /** Progress within the current band, 0–100. */
  pctToNext: number
}

/** Sub tiers earn 1 / 2 / 6 points. */
export const PLUS_TIER_POINTS = { t1: 1, t2: 2, t3: 6 } as const

export interface PlusShortfall {
  /** Points still needed for the next split. */
  points: number
  /** Subs of each tier that would close the gap on their own. */
  t1: number
  t2: number
  t3: number
}

export function subsToClose(remainingPoints: number): PlusShortfall {
  const p = Math.max(0, remainingPoints)
  return {
    points: p,
    t1: p,
    t2: Math.ceil(p / PLUS_TIER_POINTS.t2),
    t3: Math.ceil(p / PLUS_TIER_POINTS.t3),
  }
}

export function plusProgress(points: number): PlusProgress {
  const p = Math.max(0, points)
  if (p >= PLUS_TIER2_POINTS) {
    return { split: '70/30', nextThreshold: null, remaining: 0, pctToNext: 100 }
  }
  if (p >= PLUS_TIER1_POINTS) {
    const span = PLUS_TIER2_POINTS - PLUS_TIER1_POINTS
    return {
      split: '60/40',
      nextThreshold: PLUS_TIER2_POINTS,
      remaining: PLUS_TIER2_POINTS - p,
      pctToNext: ((p - PLUS_TIER1_POINTS) / span) * 100,
    }
  }
  return {
    split: '50/50',
    nextThreshold: PLUS_TIER1_POINTS,
    remaining: PLUS_TIER1_POINTS - p,
    pctToNext: (p / PLUS_TIER1_POINTS) * 100,
  }
}
