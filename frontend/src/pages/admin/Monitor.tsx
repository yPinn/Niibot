import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'

import { getContainerLogs, getLogContainers, type LogLine } from '@/api/admin'
import { PageMain } from '@/components/PageMain'
import { Icon, SlideUp, Spinner } from '@/components/primitives'
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Separator,
  Skeleton,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useAbortableFetch } from '@/hooks/useAbortableFetch'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'
import { formatStartedAt, formatUptime } from '@/lib/format'

import { DbConsole } from './monitor/DbConsole'
import { LogLineRow } from './monitor/LogLineRow'
import {
  DEFAULT_CONTAINERS,
  getLineLevel,
  LEVEL_FILTER_OPTS,
  LEVEL_ORDER,
  type LevelFilter,
  levelPillClass,
} from './monitor/logParsers'
import { EnvBadge, FieldRow, StatusBadge, VersionText } from './monitor/StatusCards'

// ── Fetch state ───────────────────────────────────────────────────────────────

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

const DASH = <span className="text-muted-foreground/40">—</span>

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminMonitor() {
  useDocumentTitle('Monitor')

  const { guard, newToken } = useAbortableFetch()

  // ── Logs state ──────────────────────────────────────────────────────────────
  const [containers, setContainers] = useState(DEFAULT_CONTAINERS)
  const [selected, setSelected] = useState('__status__')
  const tail = 200
  const followRef = useRef(true)
  const [isFollowing, setIsFollowing] = useState(true)
  const [{ loading, lines, error }, dispatch] = useReducer(fetchReducer, {
    loading: false,
    lines: [],
    error: null,
  })
  const termRef = useRef<HTMLDivElement>(null)
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('INFO')
  const [tabOrder, setTabOrder] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('monitor-tab-order')
      if (saved) {
        const parsed: unknown = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.every(x => typeof x === 'string')) return parsed
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
    const token = newToken()
    getLogContainers()
      .then(cs => guard(token, () => setContainers(cs)))
      .catch(() => {})
  }, [guard, newToken])

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

  const isDbMode = selected === '__db__'
  const isStatusMode = selected === '__status__'
  const isLogMode = !isDbMode && !isStatusMode

  usePolling({ fetchFn: pollFetch, intervalMs: 5_000, enabled: isLogMode, skipInitialCall: true })

  const filteredLines = useMemo(() => {
    if (levelFilter === 'ALL') return lines
    const threshold = LEVEL_ORDER[levelFilter]
    return lines.filter(line => {
      const lvl = getLineLevel(line.text)
      return lvl === null || LEVEL_ORDER[lvl] >= threshold
    })
  }, [lines, levelFilter])

  useEffect(() => {
    if (isFollowing && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight
    }
  }, [filteredLines, isFollowing])

  const sortedContainers = useMemo(
    () =>
      [...containers].sort((a, b) => {
        const ai = tabOrder.indexOf(a.name)
        const bi = tabOrder.indexOf(b.name)
        return (ai === -1 ? Infinity : ai) - (bi === -1 ? Infinity : bi)
      }),
    [containers, tabOrder]
  )

  const handleDragEnd = useCallback(() => {
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
  }, [])

  const handleRefresh = () => {
    const token = newToken()
    dispatch({ type: 'start' })
    getContainerLogs(selected, tail)
      .then(data => guard(token, () => dispatch({ type: 'done', lines: data.lines })))
      .catch(e =>
        guard(token, () =>
          dispatch({ type: 'fail', error: e instanceof Error ? e.message : String(e) })
        )
      )
  }

  const handleScroll = useCallback(() => {
    if (!termRef.current) return
    const el = termRef.current
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    if (atBottom !== followRef.current) {
      followRef.current = atBottom
      setIsFollowing(atBottom)
    }
  }, [])

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
              <div className="hidden lg:flex items-center gap-0.5">
                {LEVEL_FILTER_OPTS.map(lvl => (
                  <button
                    key={lvl}
                    onClick={() => setLevelFilter(lvl)}
                    className={`px-2 py-0.5 rounded text-label font-mono transition-colors select-none ${levelPillClass(lvl, levelFilter === lvl)}`}
                  >
                    {lvl === 'WARNING' ? 'WARN' : lvl}
                  </button>
                ))}
              </div>
              <div className="hidden lg:block w-px h-4 bg-border/50 shrink-0" />
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
              setLevelFilter('INFO')
              followRef.current = true
              setIsFollowing(true)
              if (v === '__status__') refreshStatus()
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

        {/* Mobile filter row — only visible below lg when on a log tab */}
        {isLogMode && (
          <div className="lg:hidden flex items-center gap-0.5 px-page py-1.5 border-b border-border/30 overflow-x-auto shrink-0">
            {LEVEL_FILTER_OPTS.map(lvl => (
              <button
                key={lvl}
                onClick={() => setLevelFilter(lvl)}
                className={`px-2 py-0.5 rounded text-label font-mono transition-colors select-none shrink-0 ${levelPillClass(lvl, levelFilter === lvl)}`}
              >
                {lvl === 'WARNING' ? 'WARN' : lvl}
              </button>
            ))}
          </div>
        )}

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
              onScroll={handleScroll}
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
              ) : filteredLines.length === 0 ? (
                <div className="px-4 py-3 text-muted-foreground">
                  No {levelFilter} lines in {lines.length} fetched.
                </div>
              ) : (
                <div className="min-w-max">
                  {filteredLines.map((line, i) => (
                    <LogLineRow key={i} line={line} index={i} isPgMode={selected === 'nb-pg'} />
                  ))}
                </div>
              )}
            </div>

            {/* Status bar */}
            <div className="flex items-center justify-between px-page lg:px-page-lg py-1.5 border-t border-border/20 bg-background shrink-0">
              <span className="font-mono text-label text-muted-foreground">
                {lines.length === 0
                  ? '—'
                  : levelFilter === 'ALL'
                    ? `${lines.length} lines`
                    : `${filteredLines.length} / ${lines.length} lines`}
              </span>
              {isFollowing && (
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
