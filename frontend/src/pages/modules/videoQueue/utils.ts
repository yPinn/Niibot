export const MIN_VIEW_COUNT_OPTIONS = [
  { value: 0, label: '不限制' },
  { value: 500, label: '500+' },
  { value: 1_000, label: '1,000+' },
  { value: 5_000, label: '5,000+' },
  { value: 10_000, label: '10,000+' },
] as const

// redemption (channel points): starts at 1 video, up to 3 videos
export const REDEMPTION_DURATION_OPTIONS = [
  { value: 300, label: '5 分鐘' },
  { value: 600, label: '10 分鐘' },
  { value: 900, label: '15 分鐘' },
] as const

/** Snap a raw seconds value to the nearest option in the list. */
export function snapToOption(options: readonly { value: number }[], value: number): number {
  return options.reduce((prev, curr) =>
    Math.abs(curr.value - value) < Math.abs(prev.value - value) ? curr : prev
  ).value
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function clampValue(value: string, min: number, max: number): string {
  const n = parseInt(value, 10)
  if (isNaN(n)) return String(min)
  return String(Math.min(max, Math.max(min, n)))
}
