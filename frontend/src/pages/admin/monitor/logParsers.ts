import AnsiToHtml from 'ansi-to-html'

import type { LogContainer } from '@/api/admin'

export const DEFAULT_CONTAINERS: LogContainer[] = [
  { name: 'nb-api', label: 'API', running: false },
  { name: 'nb-twitch', label: 'Twitch', running: false },
  { name: 'nb-discord', label: 'Discord', running: false },
  { name: 'nb-pg', label: 'Postgres', running: false },
  { name: 'nb-scrapling', label: 'Scrapling', running: false },
  { name: 'nb-instafix', label: 'Instafix', running: false },
]

export const ansiConverter = new AnsiToHtml({
  fg: '#d4d4d8',
  bg: 'transparent',
  newline: false,
  escapeXML: true,
  stream: false,
})

// Non-global for test() to avoid lastIndex state bug; global for replace()
// eslint-disable-next-line no-control-regex
const ANSI_TEST_RE = /\x1b\[[\d;]*[A-Za-z]/
// eslint-disable-next-line no-control-regex
const ANSI_STRIP_RE = /\x1b\[[\d;]*[A-Za-z]/g
// Factory for per-call stateful regex (g flag carries lastIndex; must not be shared across calls)
// eslint-disable-next-line no-control-regex
const makeAnsiRe = () => /\x1b\[[\d;]*[A-Za-z]/g

export function hasAnsi(s: string): boolean {
  return ANSI_TEST_RE.test(s)
}

export function stripAnsi(s: string): string {
  return s.replace(ANSI_STRIP_RE, '')
}

// Walk an ANSI string and return everything after the first `n` plain (non-ANSI) characters.
// Used to split a known-length plain prefix from an ANSI-colored string without losing body colors.
export function sliceAfterPlainChars(s: string, n: number): string {
  const RE = makeAnsiRe()
  let plain = 0
  let i = 0
  while (i < s.length && plain < n) {
    RE.lastIndex = i
    const m = RE.exec(s)
    if (m !== null && m.index === i) {
      i += m[0].length
    } else {
      i++
      plain++
    }
  }
  return s.slice(i)
}

// Return the first `n` plain-character prefix of an ANSI string (ANSI codes preserved).
// Companion to sliceAfterPlainChars — together they split an ANSI string at a plain-text boundary.
export function sliceBeforePlainChars(s: string, n: number): string {
  const RE = makeAnsiRe()
  let plain = 0
  let i = 0
  while (i < s.length && plain < n) {
    RE.lastIndex = i
    const m = RE.exec(s)
    if (m !== null && m.index === i) {
      i += m[0].length
    } else {
      i++
      plain++
    }
  }
  return s.slice(0, i)
}

// Trim Rich's column-alignment whitespace from the start of continuation lines.
// Uses sliceAfterPlainChars so any ANSI colors in the body are preserved.
export function trimLeadingSpaces(s: string): string {
  const clean = stripAnsi(s)
  const n = clean.length - clean.trimStart().length
  return n > 0 ? sliceAfterPlainChars(s, n) : s
}

export function parseDockerTs(raw: string): { ts: string; msg: string } {
  const m = raw.match(/^(\d{4})-(\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})\.\S+\s*(.*)$/)
  if (m) return { ts: `${m[2]} ${m[3]}`, msg: m[4] }
  return { ts: '', msg: raw }
}

// Matches PostgreSQL's own log prefix inside Docker's message payload:
// "2026-05-15 01:39:23.531 UTC [28] LOG:  ..."
const PG_PREFIX_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ UTC \[(\d+)\] ([A-Z]+):\s*/

export function parsePgPrefix(msg: string): { pid: string; level: string; body: string } | null {
  const m = msg.match(PG_PREFIX_RE)
  if (!m) return null
  return { pid: m[1], level: m[2], body: msg.slice(m[0].length) }
}

export function pgLevelColor(level: string): string {
  if (/^(ERROR|FATAL|PANIC)$/.test(level)) return 'text-status-offline'
  if (level === 'WARNING') return 'text-status-warning'
  if (level === 'NOTICE') return 'text-status-info'
  if (level === 'DEBUG') return 'text-log-dim'
  return 'text-log-muted'
}

export function pgContentColor(level: string): string {
  if (/^(ERROR|FATAL|PANIC)$/.test(level)) return 'text-status-offline'
  if (level === 'WARNING') return 'text-status-warning'
  return 'text-log-base'
}

// Matches Python/Rich structured log prefix (applied to ANSI-stripped string):
// "[2026-05-16 10:53:46] INFO  ..." — Rich renders timestamp + level with ANSI codes,
// so we strip ANSI before matching, then use sliceAfterPlainChars to extract the body
// from the original string (preserving any ANSI colors in the message body).
const PY_PREFIX_RE = /^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+([A-Z]+)\s+/

export function parsePyPrefix(msg: string): { level: string; body: string } | null {
  const clean = stripAnsi(msg)
  const m = clean.match(PY_PREFIX_RE)
  if (!m) return null
  return { level: m[2], body: sliceAfterPlainChars(msg, m[0].length) }
}

// Split a Rich/Python log body ("module_tag │ message") produced by _ModuleFormatter.
// isOwn: true when the module tag contains cyan ANSI (\x1b[36m) = first-party logger.
export function parsePyBody(
  body: string
): { module: string; isOwn: boolean; message: string } | null {
  const clean = stripAnsi(body)
  const sepIdx = clean.indexOf(' │ ')
  if (sepIdx === -1) return null
  const moduleAnsi = sliceBeforePlainChars(body, sepIdx)
  return {
    module: clean.slice(0, sepIdx).trim(),
    // eslint-disable-next-line no-control-regex
    isOwn: /\x1b\[(?:\d+;)*36m/.test(moduleAnsi),
    message: sliceAfterPlainChars(body, sepIdx + 3),
  }
}

export function pyLevelColor(level: string): string {
  if (/^(ERROR|CRITICAL|FATAL)$/.test(level)) return 'text-status-offline'
  if (level === 'WARNING') return 'text-status-warning'
  if (level === 'DEBUG') return 'text-log-dim'
  return 'text-status-info'
}

export function pyContentColor(level: string): string {
  if (/^(ERROR|CRITICAL|FATAL)$/.test(level)) return 'text-status-offline'
  if (level === 'WARNING') return 'text-status-warning'
  return 'text-log-base'
}

export function lineColor(msg: string): string {
  if (/\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b/i.test(msg)) return 'text-status-offline'
  if (/\bwarn(ing)?\b/i.test(msg)) return 'text-status-warning'
  if (/\bdebug\b/i.test(msg)) return 'text-log-muted'
  return 'text-log-base'
}

// ── Level filter ──────────────────────────────────────────────────────────────

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
export type LevelFilter = 'ALL' | LogLevel
export const LEVEL_FILTER_OPTS: LevelFilter[] = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR']
export const LEVEL_ORDER: Record<LogLevel, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 }

export function getLineLevel(text: string): LogLevel | null {
  const { msg } = parseDockerTs(text)
  const raw = msg || text
  const pg = parsePgPrefix(raw)
  if (pg) {
    if (/^(ERROR|FATAL|PANIC)$/.test(pg.level)) return 'ERROR'
    if (pg.level === 'WARNING') return 'WARNING'
    if (pg.level === 'DEBUG') return 'DEBUG'
    return 'INFO'
  }
  const py = parsePyPrefix(raw)
  if (py) {
    if (/^(ERROR|CRITICAL|FATAL)$/.test(py.level)) return 'ERROR'
    if (py.level === 'WARNING') return 'WARNING'
    if (py.level === 'DEBUG') return 'DEBUG'
    return 'INFO'
  }
  return null
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
