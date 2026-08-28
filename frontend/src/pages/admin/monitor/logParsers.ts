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
