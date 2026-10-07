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

/** Split a stored Bilibili id back into (bvid, page) — frontend mirror of the
 *  backend's `split_bilibili_id` (shared/video_sources.py). A multi-part
 *  video's non-first part is stored as `BVxxxxxxxxxx_pN`; anything else,
 *  including every id stored before multi-part support existed, is page 1. */
export function splitBilibiliId(videoId: string): [bvid: string, page: number] {
  const m = /_p(\d+)$/.exec(videoId)
  return m ? [videoId.slice(0, m.index), Number(m[1])] : [videoId, 1]
}

/** Canonical watch URL for a queued entry — frontend mirror of the backend's
 *  `build_watch_url` (shared/video_sources.py). */
export function watchUrl(videoType: string, videoId: string, startSeconds = 0): string {
  const t = startSeconds > 0 ? startSeconds : 0
  switch (videoType) {
    case 'twitch_clip':
      return `https://clips.twitch.tv/${videoId}`
    case 'twitch_vod': {
      const url = `https://www.twitch.tv/videos/${videoId}`
      return t ? `${url}?t=${t}s` : url
    }
    case 'bilibili': {
      const [bvid, page] = splitBilibiliId(videoId)
      const params = [page > 1 ? `p=${page}` : '', t ? `t=${t}` : ''].filter(Boolean)
      const url = `https://www.bilibili.com/video/${bvid}`
      return params.length ? `${url}?${params.join('&')}` : url
    }
    case 'instagram_reel':
      return `https://www.instagram.com/reel/${videoId}/`
    default:
      return t ? `https://youtu.be/${videoId}?t=${t}` : `https://youtu.be/${videoId}`
  }
}

interface SegmentFields {
  start_seconds: number
  duration_seconds: number | null
}

/** `1:30–4:00` for an entry that plays from a start point; null for a whole
 *  video (start 0 — its length column already says everything). */
export function segmentLabel({ start_seconds, duration_seconds }: SegmentFields): string | null {
  if (!start_seconds) return null
  const end = duration_seconds ? formatDuration(start_seconds + duration_seconds) : ''
  return `${formatDuration(start_seconds)}–${end}`
}

/** Submission text that re-requests the same segment (`<url> 1:30-4:00`), in
 *  the chat time syntax the backend parses (shared/video_segments.py). */
export function requeueText(
  entry: SegmentFields & { video_type: string; video_id: string }
): string {
  const url = watchUrl(entry.video_type, entry.video_id)
  const { start_seconds: start, duration_seconds: duration } = entry
  if (!start) return url
  return duration
    ? `${url} ${formatDuration(start)}-${formatDuration(start + duration)}`
    : `${url} ${formatDuration(start)}`
}

/** Watch URL for a live insert (直播插播) — the channel or live video itself. */
export function liveWatchUrl(insert: {
  source_type: 'twitch_live' | 'youtube_live'
  source_id: string
}): string {
  return insert.source_type === 'twitch_live'
    ? `https://www.twitch.tv/${insert.source_id}`
    : `https://youtu.be/${insert.source_id}`
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
