import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import AnsiToHtml from 'ansi-to-html'

import {
  type DbQueryResult,
  getContainerLogs,
  getLogContainers,
  type LogContainer,
  type LogLine,
  runDbQuery,
} from '@/api/admin'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  Separator,
  Skeleton,
  SlideUp,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsList,
  TabsTrigger,
  Textarea,
} from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'

// ── Log helpers ───────────────────────────────────────────────────────────────

const DEFAULT_CONTAINERS: LogContainer[] = [
  { name: 'niibot-api', label: 'API', running: false },
  { name: 'niibot-twitch', label: 'Twitch', running: false },
  { name: 'niibot-discord', label: 'Discord', running: false },
  { name: 'niibot-postgres', label: 'Postgres', running: false },
  { name: 'niibot-scrapling', label: 'Scrapling', running: false },
  { name: 'niibot-instafix', label: 'Instafix', running: false },
]

type FetchState = { loading: boolean; lines: LogLine[]; error: string | null }
type FetchAction =
  | { type: 'start' }
  | { type: 'done'; lines: LogLine[] }
  | { type: 'fail'; error: string }

function fetchReducer(state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'start':
      return { ...state, loading: true, error: null }
    case 'done':
      return { loading: false, lines: action.lines, error: null }
    case 'fail':
      return { ...state, loading: false, error: action.error }
  }
}

const ansiConverter = new AnsiToHtml({
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

function hasAnsi(s: string): boolean {
  return ANSI_TEST_RE.test(s)
}

function stripAnsi(s: string): string {
  return s.replace(ANSI_STRIP_RE, '')
}

function parseDockerTs(raw: string): { ts: string; msg: string } {
  const m = raw.match(/^(\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2}))\.\S+Z?\s*(.*)$/)
  if (m) return { ts: m[2], msg: m[3] }
  return { ts: '', msg: raw }
}

// Matches PostgreSQL's own log prefix inside Docker's message payload:
// "2026-05-15 01:39:23.531 UTC [28] LOG:  ..."
const PG_PREFIX_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ UTC \[(\d+)\] ([A-Z]+):\s*/

function parsePgPrefix(msg: string): { pid: string; level: string; body: string } | null {
  const m = msg.match(PG_PREFIX_RE)
  if (!m) return null
  return { pid: m[1], level: m[2], body: msg.slice(m[0].length) }
}

function pgLevelColor(level: string): string {
  if (/^(ERROR|FATAL|PANIC)$/.test(level)) return 'text-red-400'
  if (level === 'WARNING') return 'text-amber-300'
  if (level === 'DEBUG') return 'text-muted-foreground/60'
  return 'text-muted-foreground/50'
}

function lineColor(msg: string, stream: string): string {
  if (/\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b/i.test(msg)) return 'text-red-400'
  if (/\bwarn(ing)?\b/i.test(msg)) return 'text-amber-300'
  if (/\bdebug\b/i.test(msg)) return 'text-muted-foreground'
  if (stream === 'stderr') return 'text-orange-300'
  return 'text-foreground/80'
}

function LogLineRow({ line, index }: { line: LogLine; index: number }) {
  const { ts, msg } = parseDockerTs(line.text)
  const pg = parsePgPrefix(msg || line.text)
  const content = pg ? pg.body : msg || line.text

  const colored = hasAnsi(content) ? ansiConverter.toHtml(content) : null

  const fallbackColor = colored ? '' : lineColor(stripAnsi(content), line.stream)

  return (
    <div className="flex gap-2 min-w-0 hover:bg-white/5 px-3 py-px group">
      <span className="text-muted-foreground/50 shrink-0 select-none w-10 text-right tabular-nums group-hover:text-muted-foreground/70">
        {index + 1}
      </span>
      <span className="text-muted-foreground/70 shrink-0 tabular-nums w-22">{ts}</span>
      {pg && (
        <>
          <span className="text-muted-foreground/35 shrink-0 tabular-nums select-none">
            [{pg.pid}]
          </span>
          <span className={`shrink-0 font-semibold select-none ${pgLevelColor(pg.level)}`}>
            {pg.level}
          </span>
        </>
      )}
      {colored ? (
        <span
          className="break-all whitespace-pre-wrap min-w-0"
          dangerouslySetInnerHTML={{ __html: colored }}
        />
      ) : (
        <span className={`${fallbackColor} break-all whitespace-pre-wrap min-w-0`}>
          {stripAnsi(content)}
        </span>
      )}
    </div>
  )
}

// ── DB Console ────────────────────────────────────────────────────────────────

interface DbPreset {
  label: string
  sql: string
}

interface DbPresetGroup {
  group: string
  items: DbPreset[]
}

const DB_PRESETS: DbPresetGroup[] = [
  {
    group: 'Core',
    items: [
      {
        label: 'Channels',
        sql: 'SELECT channel_id, channel_name, display_name, enabled, created_at\nFROM channels\nORDER BY enabled DESC, channel_name\nLIMIT 100;',
      },
      {
        label: 'Tokens',
        sql: 'SELECT user_id, token_type, scopes, created_at, updated_at\nFROM tokens\nORDER BY updated_at DESC\nLIMIT 50;',
      },
      {
        label: 'Users',
        sql: 'SELECT id, display_name, avatar, created_at\nFROM users\nORDER BY created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Linked Accounts',
        sql: 'SELECT platform, platform_user_id, username, created_at\nFROM user_linked_accounts\nORDER BY created_at DESC\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Bot Config',
    items: [
      {
        label: 'Commands',
        sql: 'SELECT channel_id, command_name, command_type, enabled,\n       custom_response, min_role, usage_count\nFROM command_configs\nORDER BY channel_id, command_name\nLIMIT 200;',
      },
      {
        label: 'Cmd Aliases',
        sql: 'SELECT cc.channel_id, ca.alias, cc.command_name AS target_command, cc.command_type\nFROM command_aliases ca\nJOIN command_configs cc ON ca.command_id = cc.id\nORDER BY cc.channel_id, ca.alias\nLIMIT 100;',
      },
      {
        label: 'Cmd Stats',
        sql: 'SELECT channel_id, command_name, SUM(usage_count) AS total_uses\nFROM command_stats\nGROUP BY channel_id, command_name\nORDER BY total_uses DESC\nLIMIT 100;',
      },
      {
        label: 'Redemptions',
        sql: 'SELECT channel_id, action_type, reward_name, enabled\nFROM redemption_configs\nORDER BY channel_id\nLIMIT 100;',
      },
      {
        label: 'Event Configs',
        sql: 'SELECT channel_id, event_type, enabled\nFROM event_configs\nORDER BY channel_id, event_type\nLIMIT 100;',
      },
      {
        label: 'Timers',
        sql: 'SELECT channel_id, timer_name AS name, enabled, interval_seconds, message_template\nFROM timers\nORDER BY channel_id\nLIMIT 100;',
      },
      {
        label: 'Triggers',
        sql: 'SELECT channel_id, trigger_name AS name, enabled, pattern, response, usage_count\nFROM message_triggers\nORDER BY channel_id\nLIMIT 100;',
      },
    ],
  },
  {
    group: 'Analytics',
    items: [
      {
        label: 'Sessions',
        sql: 'SELECT * FROM v_session_summary\nORDER BY session_id DESC\nLIMIT 50;',
      },
      {
        label: 'Stream Events',
        sql: 'SELECT session_id, channel_id, event_type, username, display_name, occurred_at\nFROM stream_events\nORDER BY occurred_at DESC\nLIMIT 100;',
      },
      {
        label: 'Chatters',
        sql: 'SELECT channel_id, username, display_name, message_count, watch_seconds, last_message_at\nFROM chatter_stats\nORDER BY message_count DESC\nLIMIT 100;',
      },
      {
        label: 'Viewer Status',
        sql: 'SELECT channel_id, username, display_name,\n       is_subscribed, sub_tier, is_mod, is_vip, is_banned, follow_since\nFROM viewer_channel_status\nORDER BY channel_id\nLIMIT 100;',
      },
      {
        label: 'Attend. Streaks',
        sql: 'SELECT channel_id, user_id, streak_count, updated_at\nFROM viewer_attendance_streaks\nORDER BY streak_count DESC\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Features',
    items: [
      {
        label: 'Game Queue',
        sql: 'SELECT e.*,\n       s.enabled AS queue_open, s.group_size\nFROM game_queue_entries e\nLEFT JOIN game_queue_settings s ON e.channel_id = s.channel_id\nORDER BY e.channel_id, e.redeemed_at\nLIMIT 100;',
      },
      {
        label: 'Video Queue',
        sql: 'SELECT q.id, q.channel_id, q.video_type, q.video_id, q.title,\n       q.requested_by, q.status, q.created_at,\n       s.enabled AS queue_open, s.max_queue_size, s.max_duration_redemption\nFROM video_queue q\nLEFT JOIN video_queue_settings s ON q.channel_id = s.channel_id\nORDER BY q.created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Crosshairs',
        sql: 'SELECT id, channel_id, game, name, code, copy_count, created_at\nFROM crosshairs\nORDER BY copy_count DESC\nLIMIT 100;',
      },
    ],
  },
  {
    group: 'Activation',
    items: [
      {
        label: 'Codes',
        sql: 'SELECT platform_user_id, platform, expires_at, used_at\nFROM activation_codes\nORDER BY expires_at DESC\nLIMIT 50;',
      },
      {
        label: 'Requests',
        sql: 'SELECT ar.id, ar.platform, ar.platform_user_id, u.display_name,\n       ar.status, ar.note, ar.created_at\nFROM activation_requests ar\nLEFT JOIN users u ON ar.user_id = u.id\nORDER BY ar.created_at DESC\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Payments',
    items: [
      {
        label: 'Donations',
        sql: 'SELECT id, channel_id, amount, platform, status, message, created_at\nFROM donation_orders\nORDER BY created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Pay Configs',
        sql: 'SELECT * FROM user_payment_configs\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Discord',
    items: [
      {
        label: 'Discord Users',
        sql: 'SELECT user_id, username, display_name, created_at\nFROM discord_users\nORDER BY created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Birthdays',
        sql: 'SELECT user_id, month, day, year\nFROM discord_birthdays\nORDER BY month, day\nLIMIT 100;',
      },
      {
        label: 'BD Settings',
        sql: 'SELECT * FROM discord_birthday_settings\nLIMIT 50;',
      },
    ],
  },
]

function DbConsole() {
  const [sql, setSql] = useState(DB_PRESETS[0].items[0].sql)
  const [activePreset, setActivePreset] = useState<string>('Channels')
  const [result, setResult] = useState<DbQueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [expandedCell, setExpandedCell] = useState<`${number}-${number}` | null>(null)
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const sortedRows = useMemo(() => {
    if (!result || sortCol === null) return result?.rows ?? []
    return [...result.rows].sort((a, b) => {
      const av = a[sortCol],
        bv = b[sortCol]
      if (av === null && bv === null) return 0
      if (av === null) return 1
      if (bv === null) return -1
      const an = Number(av),
        bn = Number(bv)
      const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [result, sortCol, sortDir])

  const handleSortClick = (colIdx: number) => {
    setExpandedCell(null)
    if (sortCol === colIdx) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(colIdx)
      setSortDir('asc')
    }
  }

  const runQuery = async (q: string) => {
    setLoading(true)
    setError(null)
    setResult(null)
    setExpandedCell(null)
    setSortCol(null)
    setSortDir('asc')
    try {
      setResult(await runDbQuery(q))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handlePreset = (preset: DbPreset) => {
    setSql(preset.sql)
    setActivePreset(preset.label)
    runQuery(preset.sql)
  }

  const handleRun = () => runQuery(sql)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleRun()
    }
  }

  const statusText = error
    ? error
    : result
      ? `${result.row_count} ${result.row_count === 1 ? 'row' : 'rows'} · ${result.duration_ms.toFixed(1)}ms`
      : 'SELECT only · 500 row cap · 5s timeout'

  const statusColor = error
    ? 'text-destructive'
    : result
      ? 'text-muted-foreground'
      : 'text-muted-foreground/50'

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden bg-background">
      {/* ── Preset sidebar ── */}
      <div className="w-44 shrink-0 border-r border-border/30 overflow-y-auto flex flex-col gap-0 py-1">
        {DB_PRESETS.map(group => (
          <div key={group.group}>
            <div className="px-3 pt-3 pb-1 text-muted-foreground/60 font-medium uppercase tracking-wide text-label select-none">
              {group.group}
            </div>
            {group.items.map(item => (
              <button
                key={item.label}
                onClick={() => handlePreset(item)}
                className={`w-full text-left px-3 py-1 text-label truncate transition-colors ${
                  activePreset === item.label
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* ── Main area ── */}
      <div className="flex flex-col flex-1 min-h-0 min-w-0">
        {/* SQL input */}
        <div className="flex gap-2 p-3 border-b border-border/30 shrink-0">
          <Textarea
            value={sql}
            onChange={e => {
              setSql(e.target.value)
              setActivePreset('')
            }}
            onKeyDown={handleKeyDown}
            rows={4}
            className="flex-1 font-mono text-label text-foreground bg-muted border-border resize-y min-h-[72px] max-h-48 focus-visible:ring-1 focus-visible:ring-ring"
            placeholder="SELECT ..."
            spellCheck={false}
          />
          <Button
            size="sm"
            onClick={handleRun}
            disabled={loading || !sql.trim()}
            className="self-end shrink-0"
            title="Run (Ctrl+Enter)"
          >
            {loading ? <Spinner className="size-3" /> : <Icon icon="fa-solid fa-play" size="xs" />}
          </Button>
        </div>

        {/* Results */}
        <div className="flex-1 min-h-0 overflow-auto">
          {result && result.row_count > 0 && (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-border">
                  <TableHead className="sticky top-0 bg-muted text-muted-foreground/50 font-medium w-10 text-right tabular-nums select-none">
                    #
                  </TableHead>
                  {result.columns.map((col, j) => (
                    <TableHead
                      key={col}
                      className="sticky top-0 bg-muted text-muted-foreground whitespace-nowrap font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => handleSortClick(j)}
                    >
                      <div className="flex items-center gap-1.5">
                        {col}
                        {sortCol === j && (
                          <Icon
                            icon={`fa-solid fa-arrow-${sortDir === 'asc' ? 'up' : 'down'}`}
                            size="xs"
                          />
                        )}
                      </div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedRows.map((row, i) => (
                  <TableRow
                    key={i}
                    className="hover:bg-accent border-border/50 font-mono text-label"
                  >
                    <TableCell className="text-muted-foreground/40 text-right py-1 tabular-nums select-none">
                      {i + 1}
                    </TableCell>
                    {row.map((cell, j) => {
                      const key = `${i}-${j}` as const
                      const expanded = expandedCell === key
                      return (
                        <TableCell
                          key={j}
                          className={`py-1 ${cell !== null ? 'cursor-pointer' : ''}`}
                          onClick={() => cell !== null && setExpandedCell(expanded ? null : key)}
                        >
                          <div
                            className={
                              expanded
                                ? 'max-h-48 overflow-y-auto whitespace-pre-wrap break-all text-foreground/90 max-w-[60ch] transition-all duration-150'
                                : `max-h-6 overflow-hidden truncate max-w-[36ch] transition-all duration-150 ${cell === null ? 'text-muted-foreground/50 italic' : 'text-foreground/80'}`
                            }
                            title={!expanded && cell !== null ? String(cell) : undefined}
                          >
                            {cell === null ? 'NULL' : String(cell)}
                          </div>
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {result && result.row_count === 0 && !error && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
              <Icon icon="fa-solid fa-inbox" size="lg" />
              <span className="font-mono text-label">No rows returned.</span>
            </div>
          )}
          {!result && !error && !loading && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground/60">
              <Icon icon="fa-solid fa-terminal" size="lg" />
              <span className="font-mono text-label">Select a preset or run a query.</span>
            </div>
          )}
        </div>

        {/* Status bar */}
        <div className="flex items-center px-3 py-1.5 border-t border-border/20 bg-background shrink-0">
          <span className={`font-mono text-label truncate ${statusColor}`}>{statusText}</span>
        </div>
      </div>
    </div>
  )
}

// ── Status card helpers ───────────────────────────────────────────────────────

function formatUptime(seconds?: number): string {
  if (seconds === undefined) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${s}s`
}

function formatStartedAt(iso?: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

const DASH = <span className="text-muted-foreground/40">—</span>

function StatusBadge({ online, ready }: { online: boolean; ready?: boolean }) {
  if (!online)
    return (
      <Badge className="border-status-offline/20 bg-status-offline/10 text-status-offline gap-1.5">
        <Icon icon="fa-solid fa-circle-xmark" size="xs" />
        offline
      </Badge>
    )
  if (ready === false)
    return (
      <Badge className="border-status-loading/20 bg-status-loading/10 text-status-loading gap-1.5">
        <Icon icon="fa-solid fa-circle-half-stroke" size="xs" />
        starting
      </Badge>
    )
  return (
    <Badge className="border-status-online/20 bg-status-online/10 text-status-online gap-1.5">
      <Icon icon="fa-solid fa-circle-check" size="xs" />
      online
    </Badge>
  )
}

function EnvBadge({ env }: { env?: string }) {
  if (!env) return <span className="text-muted-foreground/40">—</span>
  const cls =
    env === 'production'
      ? 'border-status-live/20 bg-status-live/10 text-status-live'
      : env === 'staging'
        ? 'border-status-loading/20 bg-status-loading/10 text-status-loading'
        : 'border-status-info/20 bg-status-info/10 text-status-info'
  return <Badge className={`font-mono ${cls}`}>{env}</Badge>
}

function VersionText({ version, commit }: { version?: string; commit?: string }) {
  const label = version && version !== 'dev' ? version : (version ?? '—')
  const shortSha = commit && commit !== 'unknown' ? commit.slice(0, 7) : null
  return <>{shortSha && !label.includes(shortSha) ? `${label} (${shortSha})` : label}</>
}

function FieldRow({
  label,
  value,
  loading,
  offline,
}: {
  label: string
  value: React.ReactNode
  loading?: boolean
  offline?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <span className="text-label font-medium uppercase tracking-wide text-muted-foreground shrink-0">
        {label}
      </span>
      <div className="text-sub font-mono flex items-center">
        {loading ? <Skeleton className="h-4 w-20" /> : offline ? DASH : value}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminMonitor() {
  useDocumentTitle('Monitor')

  // ── Logs state ──────────────────────────────────────────────────────────────
  const [containers, setContainers] = useState<LogContainer[]>(DEFAULT_CONTAINERS)
  const [selected, setSelected] = useState('niibot-api')
  const tail = 200
  const [follow, setFollow] = useState(true)
  const [{ loading, lines, error }, dispatch] = useReducer(fetchReducer, {
    loading: false,
    lines: [],
    error: null,
  })
  const termRef = useRef<HTMLDivElement>(null)
  const [tabOrder, setTabOrder] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('monitor-tab-order')
      if (saved) {
        const parsed = JSON.parse(saved) as string[]
        if (Array.isArray(parsed)) return parsed
      }
    } catch {
      // ignore malformed localStorage value
    }
    return DEFAULT_CONTAINERS.map(c => c.name)
  })
  const dragItem = useRef<string | null>(null)
  const dragOver = useRef<string | null>(null)
  const [draggingTab, setDraggingTab] = useState<string | null>(null)

  useEffect(() => {
    getLogContainers()
      .then(cs => setContainers(cs))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (selected === '__db__' || selected === '__status__') return
    let cancelled = false
    dispatch({ type: 'start' })
    getContainerLogs(selected, tail)
      .then(data => {
        if (!cancelled) dispatch({ type: 'done', lines: data.lines })
      })
      .catch(e => {
        if (!cancelled)
          dispatch({ type: 'fail', error: e instanceof Error ? e.message : String(e) })
      })
    return () => {
      cancelled = true
    }
  }, [selected, tail])

  const pollFetch = useCallback(async () => {
    if (selected === '__db__' || selected === '__status__') return
    try {
      const data = await getContainerLogs(selected, tail)
      dispatch({ type: 'done', lines: data.lines })
    } catch {
      // silent — don't disrupt the view on transient poll failure
    }
  }, [selected, tail])

  usePolling({ fetchFn: pollFetch, intervalMs: 5_000, enabled: follow, skipInitialCall: true })

  useEffect(() => {
    if (follow && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight
    }
  }, [lines, follow])

  const isDbMode = selected === '__db__'
  const isStatusMode = selected === '__status__'
  const isLogMode = !isDbMode && !isStatusMode

  const sortedContainers = useMemo(
    () =>
      [...containers].sort((a, b) => {
        const ai = tabOrder.indexOf(a.name)
        const bi = tabOrder.indexOf(b.name)
        return (ai === -1 ? Infinity : ai) - (bi === -1 ? Infinity : bi)
      }),
    [containers, tabOrder]
  )

  const handleDragEnd = () => {
    if (dragItem.current && dragOver.current && dragItem.current !== dragOver.current) {
      setTabOrder(prev => {
        const fromIdx = prev.indexOf(dragItem.current!)
        const toIdx = prev.indexOf(dragOver.current!)
        if (fromIdx === -1 || toIdx === -1) return prev
        const next = [...prev]
        next.splice(fromIdx, 1)
        next.splice(toIdx, 0, dragItem.current!)
        localStorage.setItem('monitor-tab-order', JSON.stringify(next))
        return next
      })
    }
    dragItem.current = null
    dragOver.current = null
    setDraggingTab(null)
  }

  const handleRefresh = () => {
    dispatch({ type: 'start' })
    getContainerLogs(selected, tail)
      .then(data => dispatch({ type: 'done', lines: data.lines }))
      .catch(e => dispatch({ type: 'fail', error: e instanceof Error ? e.message : String(e) }))
  }

  // ── Status state ─────────────────────────────────────────────────────────
  const {
    twitch,
    discord,
    api,
    lastUpdate,
    initialLoading,
    refresh: refreshStatus,
  } = useServiceStatus()

  const services = useMemo(
    () => [
      {
        key: 'api',
        name: 'API Server',
        icon: 'fa-solid fa-server',
        online: api.online,
        ready: undefined as boolean | undefined,
        fields: [
          {
            label: 'version',
            value: <VersionText version={api.version} commit={api.git_commit} />,
          },
          { label: 'started', value: formatStartedAt(api.started_at) },
          { label: 'uptime', value: formatUptime(api.uptime_seconds) },
          { label: 'env', value: <EnvBadge env={api.environment} /> },
          {
            label: 'database',
            value:
              api.db_connected === undefined ? (
                DASH
              ) : api.db_connected ? (
                <span className="text-status-online">connected</span>
              ) : (
                <span className="text-status-offline">disconnected</span>
              ),
          },
        ],
      },
      {
        key: 'twitch',
        name: 'Twitch Bot',
        icon: 'fa-brands fa-twitch',
        online: twitch.online,
        ready: twitch.ready,
        fields: [
          {
            label: 'version',
            value: <VersionText version={twitch.version} commit={twitch.git_commit} />,
          },
          { label: 'started', value: formatStartedAt(twitch.started_at) },
          { label: 'uptime', value: formatUptime(twitch.uptime_seconds) },
          { label: 'bot id', value: twitch.bot_id ?? '—' },
          { label: 'channels', value: twitch.connected_channels ?? '—' },
          { label: 'features', value: twitch.components ?? '—' },
          { label: 'ai model', value: twitch.ai_model ?? '—' },
        ],
      },
      {
        key: 'discord',
        name: 'Discord Bot',
        icon: 'fa-brands fa-discord',
        online: discord.online,
        ready: discord.ready,
        fields: [
          {
            label: 'version',
            value: <VersionText version={discord.version} commit={discord.git_commit} />,
          },
          { label: 'started', value: formatStartedAt(discord.started_at) },
          { label: 'uptime', value: formatUptime(discord.uptime_seconds) },
          { label: 'bot id', value: discord.bot_id ?? '—' },
          { label: 'guilds', value: discord.guilds ?? '—' },
          { label: 'features', value: discord.cogs ?? '—' },
          { label: 'ai model', value: discord.ai_model ?? '—' },
          ...(discord.ws_latency_ms !== undefined
            ? [{ label: 'ws latency', value: `${discord.ws_latency_ms}ms` }]
            : []),
        ],
      },
    ],
    [twitch, discord, api]
  )

  return (
    <PageMain className="gap-0 p-0 lg:p-0 overflow-hidden">
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-page h-14 lg:px-page-lg border-b border-border/50 shrink-0">
          <SlideUp>
            <h1 className="text-page-title font-bold">Monitor</h1>
          </SlideUp>
          {isLogMode && (
            <div className="flex items-center gap-2">
              <span className="text-label text-muted-foreground">Follow</span>
              <Switch checked={follow} onCheckedChange={setFollow} />
              {!follow && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleRefresh}
                  disabled={loading}
                  aria-label="Refresh"
                >
                  {loading ? (
                    <Spinner />
                  ) : (
                    <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
                  )}
                </Button>
              )}
            </div>
          )}
          {isStatusMode && (
            <div className="flex items-center gap-2">
              <span className="text-label text-muted-foreground font-mono">
                {lastUpdate.toLocaleTimeString('zh-TW', { hour12: false })}
              </span>
              <Button
                variant="ghost"
                size="icon"
                onClick={refreshStatus}
                aria-label="Refresh status"
              >
                <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
              </Button>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="px-page lg:px-page-lg border-b border-border/50 overflow-x-auto shrink-0">
          <Tabs
            value={selected}
            onValueChange={v => {
              setSelected(v)
              setFollow(false)
            }}
          >
            <TabsList variant="line" className="h-10 bg-transparent gap-0">
              <TabsTrigger value="__status__" className="text-label px-3">
                <Icon icon="fa-solid fa-gauge" size="xs" />
                Status
              </TabsTrigger>
              {sortedContainers.map(c => (
                <TabsTrigger
                  key={c.name}
                  value={c.name}
                  className={`text-label px-3 cursor-grab select-none${draggingTab === c.name ? ' opacity-40' : ''}`}
                  draggable
                  onDragStart={() => {
                    dragItem.current = c.name
                    setDraggingTab(c.name)
                  }}
                  onDragEnter={() => {
                    dragOver.current = c.name
                  }}
                  onDragOver={e => e.preventDefault()}
                  onDragEnd={handleDragEnd}
                >
                  <span
                    className={`size-1.5 rounded-full shrink-0 ${c.running ? 'bg-status-online' : 'bg-muted-foreground/50'}`}
                  />
                  {c.label}
                </TabsTrigger>
              ))}
              <TabsTrigger value="__db__" className="text-label px-3">
                <Icon icon="fa-solid fa-database" size="xs" />
                DB
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Content */}
        {isStatusMode ? (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-section p-page lg:p-page-lg">
              {services.map(service => (
                <Card key={service.key}>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <Icon
                        icon={service.icon}
                        size="sm"
                        wrapperClassName="text-muted-foreground"
                      />
                      <CardTitle className="text-card-title">{service.name}</CardTitle>
                    </div>
                    <CardAction>
                      {initialLoading ? (
                        <Skeleton className="h-5 w-16 rounded-full" />
                      ) : (
                        <StatusBadge online={service.online} ready={service.ready} />
                      )}
                    </CardAction>
                  </CardHeader>
                  <CardContent>
                    {service.fields.map((field, idx) => (
                      <div key={field.label}>
                        {idx > 0 && <Separator className="opacity-40" />}
                        <FieldRow
                          label={field.label}
                          value={field.value}
                          loading={initialLoading}
                          offline={!service.online}
                        />
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ) : isDbMode ? (
          <DbConsole />
        ) : (
          <div className="dark flex flex-col flex-1 min-h-0">
            <div
              ref={termRef}
              className="flex-1 min-h-0 overflow-auto bg-background font-mono text-label leading-5 py-2"
            >
              {loading && lines.length === 0 ? (
                <div className="flex items-center gap-2 px-4 py-3 text-muted-foreground">
                  <Spinner className="size-3" />
                  <span>Loading logs…</span>
                </div>
              ) : error ? (
                <div className="px-4 py-3 text-destructive">{error}</div>
              ) : lines.length === 0 ? (
                <div className="px-4 py-3 text-muted-foreground">No log output.</div>
              ) : (
                lines.map((line, i) => <LogLineRow key={i} line={line} index={i} />)
              )}
            </div>

            {/* Status bar */}
            <div className="flex items-center justify-between px-page lg:px-page-lg py-1.5 border-t border-border/20 bg-background shrink-0">
              <span className="font-mono text-label text-muted-foreground">
                {lines.length > 0 ? `${lines.length} lines` : '—'}
              </span>
              {follow && (
                <span className="font-mono text-label text-status-online flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-status-online animate-pulse" />
                  live
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </PageMain>
  )
}
