export const MIN_VIEW_COUNT_OPTIONS = [
  { value: 0, label: '不限制' },
  { value: 500, label: '500+' },
  { value: 1_000, label: '1,000+' },
  { value: 5_000, label: '5,000+' },
  { value: 10_000, label: '10,000+' },
] as const

// redemption (channel points) length cap — default 10 分鐘
export const REDEMPTION_DURATION_OPTIONS = [
  { value: 300, label: '5 分鐘' },
  { value: 600, label: '10 分鐘' },
  { value: 900, label: '15 分鐘' },
  { value: 1200, label: '20 分鐘' },
] as const

/** How many rows each tab of the queue card shows per page. */
export const QUEUE_PAGE_SIZE = 10

/** Snap a raw seconds value to the nearest option in the list. */
export function snapToOption(options: readonly { value: number }[], value: number): number {
  return options.reduce((prev, curr) =>
    Math.abs(curr.value - value) < Math.abs(prev.value - value) ? curr : prev
  ).value
}

/** Canonical watch URL for a queued entry — frontend mirror of the backend's
 *  `build_watch_url` (shared/video_sources.py). */
export function watchUrl(videoType: string, videoId: string): string {
  switch (videoType) {
    case 'twitch_clip':
      return `https://clips.twitch.tv/${videoId}`
    case 'bilibili':
      return `https://www.bilibili.com/video/${videoId}`
    default:
      return `https://youtu.be/${videoId}`
  }
}

/** Fallback thumbnail for a queued entry when the row has no stored
 *  `thumbnail_url` (older entries). Only YouTube has a deterministic no-auth
 *  URL; other platforms return null and the card shows a placeholder. */
export function thumbnailUrl(videoType: string, videoId: string): string | null {
  return videoType === 'youtube' ? `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg` : null
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
