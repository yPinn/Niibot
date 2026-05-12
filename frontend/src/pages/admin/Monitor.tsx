import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import AnsiToHtml from 'ansi-to-html'

import { getContainerLogs, getLogContainers, type LogContainer, type LogLine } from '@/api/admin'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Skeleton,
  SlideUp,
  Spinner,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
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
  fg: 'rgba(255,255,255,0.75)',
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

function lineColor(msg: string, stream: string): string {
  if (/\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b/i.test(msg)) return 'text-red-400'
  if (/\bwarn(ing)?\b/i.test(msg)) return 'text-amber-400'
  if (/\bdebug\b/i.test(msg)) return 'text-white/40'
  if (stream === 'stderr') return 'text-orange-300/80'
  return ''
}

function LogLineRow({ line, index }: { line: LogLine; index: number }) {
  const { ts, msg } = parseDockerTs(line.text)
  const content = msg || line.text

  const colored = useMemo(() => {
    if (hasAnsi(content)) return ansiConverter.toHtml(content)
    return null
  }, [content])

  const fallbackColor = colored ? '' : lineColor(stripAnsi(content), line.stream)

  return (
    <div className="flex gap-2 min-w-0 hover:bg-white/2 px-3 py-px group">
      <span className="text-white/20 shrink-0 select-none w-10 text-right tabular-nums group-hover:text-white/35">
        {index + 1}
      </span>
      <span className="text-white/30 shrink-0 tabular-nums w-22">{ts}</span>
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
  const [tail, setTail] = useState(200)
  const [follow, setFollow] = useState(false)
  const [{ loading, lines, error }, dispatch] = useReducer(fetchReducer, {
    loading: false,
    lines: [],
    error: null,
  })
  const termRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getLogContainers()
      .then(cs => setContainers(cs))
      .catch(() => {})
  }, [])

  useEffect(() => {
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
    try {
      const data = await getContainerLogs(selected, tail)
      dispatch({ type: 'done', lines: data.lines })
    } catch {
      // silent — don't disrupt the view on transient poll failure
    }
  }, [selected, tail])

  usePolling({ fetchFn: pollFetch, intervalMs: 5_000, enabled: follow })

  useEffect(() => {
    if (follow && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight
    }
  }, [lines, follow])

  const currentContainer = containers.find(c => c.name === selected)

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
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* ── Left: Logs panel ───────────────────────────────────────────────── */}
        <div className="flex flex-col flex-1 min-h-0 min-w-0 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between gap-3 px-page h-14 lg:px-page-lg border-b border-border/50 shrink-0">
            <SlideUp className="flex items-center gap-2.5">
              <h1 className="text-page-title font-bold">Service Logs</h1>
              {currentContainer && (
                <Badge
                  className={
                    currentContainer.running
                      ? 'border-status-online/20 bg-status-online/10 text-status-online gap-1.5'
                      : 'border-status-offline/20 bg-status-offline/10 text-status-offline gap-1.5'
                  }
                >
                  <Icon
                    icon={
                      currentContainer.running ? 'fa-solid fa-circle' : 'fa-solid fa-circle-xmark'
                    }
                    size="xs"
                  />
                  {currentContainer.running ? 'running' : 'stopped'}
                </Badge>
              )}
            </SlideUp>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-label text-muted-foreground">Follow</span>
                <Switch checked={follow} onCheckedChange={setFollow} />
              </div>
              <Select value={String(tail)} onValueChange={v => setTail(Number(v))}>
                <SelectTrigger size="sm" className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="50">50 lines</SelectItem>
                  <SelectItem value="100">100 lines</SelectItem>
                  <SelectItem value="200">200 lines</SelectItem>
                  <SelectItem value="500">500 lines</SelectItem>
                  <SelectItem value="1000">1000 lines</SelectItem>
                </SelectContent>
              </Select>
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
            </div>
          </div>

          {/* Container tabs */}
          <div className="px-page lg:px-page-lg border-b border-border/50 overflow-x-auto shrink-0">
            <Tabs
              value={selected}
              onValueChange={v => {
                setSelected(v)
                setFollow(false)
              }}
            >
              <TabsList variant="line" className="h-10 bg-transparent gap-0">
                {containers.map(c => (
                  <TabsTrigger key={c.name} value={c.name} className="gap-1.5 text-label px-3">
                    <span
                      className={`size-1.5 rounded-full shrink-0 ${c.running ? 'bg-status-online' : 'bg-muted-foreground/50'}`}
                    />
                    {c.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

          {/* Terminal */}
          <div
            ref={termRef}
            className="flex-1 min-h-0 overflow-auto bg-zinc-900 font-mono text-label leading-5 py-2"
          >
            {loading && lines.length === 0 ? (
              <div className="flex items-center gap-2 px-4 py-3 text-white/40">
                <Spinner className="size-3" />
                <span>Loading logs…</span>
              </div>
            ) : error ? (
              <div className="px-4 py-3 text-red-400">{error}</div>
            ) : lines.length === 0 ? (
              <div className="px-4 py-3 text-white/35">No log output.</div>
            ) : (
              lines.map((line, i) => <LogLineRow key={i} line={line} index={i} />)
            )}
          </div>

          {/* Status bar */}
          <div className="flex items-center justify-between px-page lg:px-page-lg py-1.5 border-t border-border/20 bg-zinc-900 shrink-0">
            <span className="font-mono text-label text-white/30">
              {lines.length > 0 ? `${lines.length} lines · ${selected}` : selected}
            </span>
            {follow && (
              <span className="font-mono text-label text-status-online flex items-center gap-1.5">
                <Icon icon="fa-solid fa-circle" size="xs" />
                following
              </span>
            )}
          </div>
        </div>

        {/* ── Right: Status cards ─────────────────────────────────────────────── */}
        <div className="hidden lg:flex flex-col w-85 xl:w-95 shrink-0 border-l border-border/50 overflow-y-auto">
          {/* Panel header */}
          <div className="flex items-center justify-between px-page h-14 border-b border-border/50 shrink-0">
            <h2 className="text-page-title font-bold">System Status</h2>
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
          </div>

          {/* Cards */}
          <div className="flex flex-col gap-section p-page">
            {services.map(service => (
              <Card key={service.key}>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Icon icon={service.icon} size="sm" wrapperClassName="text-muted-foreground" />
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
      </div>
    </PageMain>
  )
}
