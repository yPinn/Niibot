import AnsiToHtml from 'ansi-to-html'

import type { LogContainer, LogLevel } from '@/api/admin'

export const DEFAULT_CONTAINERS: LogContainer[] = [
  { name: 'nb-api', label: 'API', running: false },
  { name: 'nb-twitch', label: 'Twitch', running: false },
  { name: 'nb-discord', label: 'Discord', running: false },
  { name: 'nb-pg', label: 'Postgres', running: false },
  { name: 'nb-instafix', label: 'Instafix', running: false },
]

// ── ANSI (only `source: 'raw'` records still carry escape codes) ──────────────

export const ansiConverter = new AnsiToHtml({
  fg: '#d4d4d8',
  bg: 'transparent',
  newline: false,
  escapeXML: true,
  stream: false,
})

// eslint-disable-next-line no-control-regex
const ANSI_RE = /\x1b\[[\d;]*[A-Za-z]/
// eslint-disable-next-line no-control-regex
const ANSI_RE_G = /\x1b\[[\d;]*[A-Za-z]/g

export const hasAnsi = (s: string): boolean => ANSI_RE.test(s)
export const stripAnsi = (s: string): string => s.replace(ANSI_RE_G, '')

// ── Level filter ─────────────────────────────────────────────────────────────

export type LevelFilter = 'ALL' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
export const LEVEL_FILTER_OPTS: LevelFilter[] = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR']

/** Colour for the fixed-width LEVEL label column only. */
export function levelColor(level: LogLevel): string {
  switch (level) {
    case 'ERROR':
    case 'CRITICAL':
      return 'text-status-offline'
    case 'WARNING':
      return 'text-status-warning'
    case 'DEBUG':
      return 'text-log-dim'
    case 'INFO':
      return 'text-status-info'
    default:
      return 'text-log-muted'
  }
}

/** Colour for the message body — kept neutral so importance reads off the row
 *  tint, not a wall of coloured text. */
export function levelMessageColor(level: LogLevel): string {
  if (level === 'DEBUG') return 'text-log-dim'
  if (level === 'UNKNOWN') return 'text-log-muted'
  return 'text-log-base'
}

/** Whole-row treatment: tint + left rule by importance. INFO is the baseline
 *  (no tint). A stderr line that isn't itself an error gets a neutral rule so
 *  "came from stderr" stays visible without looking like a failure. */
export function levelRowClass(level: LogLevel, stream: 'stdout' | 'stderr', isPg: boolean): string {
  switch (level) {
    case 'CRITICAL':
      return 'bg-status-offline/15 border-l-2 border-status-offline'
    case 'ERROR':
      return 'bg-status-offline/8 border-l-2 border-status-offline/60'
    case 'WARNING':
      return 'bg-status-warning/8 border-l-2 border-status-warning/50'
    case 'DEBUG':
      return 'opacity-60'
    default:
      return stream === 'stderr' && !isPg ? 'border-l-2 border-muted-foreground/30' : ''
  }
}

/** Parse the server `ts` (`"2026-08-28 08:05:19"` — UTC, from docker's
 *  `timestamps=1`) into local wall-clock parts. Returns null when unparseable
 *  so the caller can show a placeholder instead of guessing. */
export function formatLogTime(ts: string): { time: string; date: string } | null {
  if (!ts) return null
  const d = new Date(ts.includes('T') ? ts : `${ts.replace(' ', 'T')}Z`)
  if (Number.isNaN(d.getTime())) return null
  const p = (n: number): string => String(n).padStart(2, '0')
  return {
    time: `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`,
    date: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`,
  }
}

export function levelPillClass(lvl: LevelFilter, active: boolean): string {
  if (active) {
    if (lvl === 'ERROR') return 'bg-status-offline/15 text-status-offline'
    if (lvl === 'WARNING') return 'bg-status-warning/15 text-status-warning'
    if (lvl === 'DEBUG') return 'bg-muted-foreground/15 text-muted-foreground'
    return 'bg-accent text-accent-foreground'
  }
  return 'text-muted-foreground/50 hover:text-muted-foreground hover:bg-accent/50'
}

/** Drop a redundant `[channel] ` prefix when the record already has `channel`. */
export function trimChannelPrefix(message: string, channel: string | null): string {
  if (channel && message.startsWith(`[${channel}] `)) {
    return message.slice(channel.length + 3)
  }
  return message
}

// ── event_class classification (常駐/偶發, see the stability-log-audit work) ──

export type EventClass = 'persistent' | 'occasional'

export function parseEventClass(value: unknown): EventClass | null {
  return value === 'persistent' || value === 'occasional' ? value : null
}

/** persistent gets the "own module" cyan treatment already used elsewhere in
 *  this viewer, since both mark "part of this service's own long-running
 *  machinery" — occasional reuses the plain neutral chip style, since most
 *  log lines are request/connection-scoped by nature and don't need to stand out. */
export function eventClassLabel(cls: EventClass): string {
  return cls === 'persistent' ? '常駐' : '偶發'
}

export function eventClassPillClass(cls: EventClass): string {
  return cls === 'persistent'
    ? 'bg-cyan-400/10 text-cyan-400/80'
    : 'bg-muted-foreground/15 text-muted-foreground'
}
