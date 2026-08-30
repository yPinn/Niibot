import { Fragment, useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'

import {
  getClientErrorGroups,
  getContainerLogs,
  getLogContainers,
  type LogRecord,
} from '@/api/admin'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, Spinner } from '@/components/primitives'
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
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'
import { formatStartedAt, formatUptime } from '@/lib/format'

import { ClientErrorsPanel } from './monitor/ClientErrorsPanel'
import { DbConsole } from './monitor/DbConsole'
import {
  DEFAULT_CONTAINERS,
  formatLogTime,
  LEVEL_FILTER_OPTS,
  type LevelFilter,
  levelPillClass,
} from './monitor/logParsers'
import { LogRecordRow } from './monitor/LogRecordRow'
import { EnvBadge, FieldRow, StatusBadge, VersionText } from './monitor/StatusCards'

// ── Fetch state ───────────────────────────────────────────────────────────────

type FetchState = { loading: boolean; records: LogRecord[]; error: string | null }
type FetchAction =
  { type: 'start' } | { type: 'done'; records: LogRecord[] } | { type: 'fail'; error: string }

function fetchReducer(state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'start':
      return { ...state, loading: true, error: null }
    case 'done':
      return { loading: false, records: action.records, error: null }
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
  const [{ loading, records, error }, dispatch] = useReducer(fetchReducer, {
    loading: false,
    records: [],
    error: null,
  })
  const termRef = useRef<HTMLDivElement>(null)
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('INFO')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim(), 300)

  // Bumped by the shared refresh button to force a reload inside the DB / Errors
  // panels; `panelLoading` mirrors the active panel's loading state for the icon.
  const [reloadNonce, setReloadNonce] = useState(0)
  const [panelLoading, setPanelLoading] = useState(false)

  useEffect(() => {
    const token = newToken()
    getLogContainers()
      .then(cs => guard(token, () => setContainers(cs)))
      .catch(() => {})
  }, [guard, newToken])

  const query = { tail, level: levelFilter, q: debouncedSearch || undefined }

  useEffect(() => {
    if (selected === '__db__' || selected === '__status__' || selected === '__errors__') return
    let cancelled = false
    dispatch({ type: 'start' })
    getContainerLogs(selected, query)
      .then(data => {
        if (!cancelled) dispatch({ type: 'done', records: data.records })
      })
      .catch(e => {
        if (!cancelled)
          dispatch({ type: 'fail', error: e instanceof Error ? e.message : String(e) })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, tail, levelFilter, debouncedSearch])

  const pollFetch = useCallback(async () => {
    if (selected === '__db__' || selected === '__status__' || selected === '__errors__') return
    try {
      const data = await getContainerLogs(selected, query)
      dispatch({ type: 'done', records: data.records })
    } catch {
      // silent — don't disrupt the view on transient poll failure
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, tail, levelFilter, debouncedSearch])

  const isDbMode = selected === '__db__'
  const isStatusMode = selected === '__status__'
  const isErrorsMode = selected === '__errors__'
  const isLogMode = !isDbMode && !isStatusMode && !isErrorsMode

  const filtersActive = levelFilter !== 'INFO' || search !== ''
  const refreshBusy = isLogMode ? loading : isStatusMode ? false : panelLoading

  usePolling({ fetchFn: pollFetch, intervalMs: 5_000, enabled: isLogMode, skipInitialCall: true })

  useEffect(() => {
    if (isFollowing && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight
    }
  }, [records, isFollowing])

  const handleRefresh = () => {
    const token = newToken()
    dispatch({ type: 'start' })
    getContainerLogs(selected, query)
      .then(data => guard(token, () => dispatch({ type: 'done', records: data.records })))
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

  const jumpToLatest = useCallback(() => {
    const el = termRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    followRef.current = true
    setIsFollowing(true)
  }, [])

  /** From the Errors tab: open the API container log filtered to one request id.
   *  request_id is bound by the API's request-context middleware, so nb-api is
   *  where the matching structured lines live. */
  const traceRequestId = useCallback(
    (requestId: string) => {
      const api = containers.find(c => c.name.startsWith('nb-api')) ?? containers[0]
      setSelected(api.name)
      setLevelFilter('ALL')
      setSearch(requestId)
      followRef.current = false
      setIsFollowing(false)
    },
    [containers]
  )

  // ── Status state ─────────────────────────────────────────────────────────
  const {
    twitch,
    discord,
    api,
    lastUpdate,
    initialLoading,
    refresh: refreshStatus,
  } = useServiceStatus()

  // Frontend-error summary shown on the Status tab (last 24h).
  // null = loading · 'error' = fetch failed · object = loaded
  const [errSummary, setErrSummary] = useState<{ total: number; kinds: number } | 'error' | null>(
    null
  )
  const loadErrSummary = useCallback(() => {
    getClientErrorGroups({ sinceHours: 24 })
      .then(gs => setErrSummary({ total: gs.reduce((n, g) => n + g.count, 0), kinds: gs.length }))
      .catch(() => setErrSummary('error'))
  }, [])
  useEffect(() => {
    loadErrSummary()
  }, [loadErrSummary])

  const refreshStatusAll = useCallback(() => {
    refreshStatus()
    loadErrSummary()
  }, [refreshStatus, loadErrSummary])

  /** One refresh button for every tab: live logs re-fetch, Status re-polls,
   *  DB / Errors panels reload via a bumped nonce. */
  const handleUnifiedRefresh = () => {
    if (isStatusMode) refreshStatusAll()
    else if (isLogMode) handleRefresh()
    else setReloadNonce(n => n + 1)
  }

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
      <div className="flex flex-col flex-1 min-h-0 min-w-0 overflow-hidden">
        {/* Tab bar — modes scroll on the left, refresh/clock pinned right */}
        <div className="flex items-stretch gap-2 px-page lg:px-page-lg border-b border-border/50 shrink-0">
          <div className="min-w-0 flex-1 overflow-x-auto">
            <Tabs
              value={selected}
              onValueChange={v => {
                setSelected(v)
                setLevelFilter('INFO')
                setPanelLoading(false)
                followRef.current = true
                setIsFollowing(true)
                if (v === '__status__') refreshStatusAll()
              }}
            >
              <TabsList variant="line" className="h-11 bg-transparent gap-0">
                <TabsTrigger value="__status__" className="text-content px-3">
                  <Icon icon="fa-solid fa-gauge" size="sm" />
                  Status
                </TabsTrigger>
                <TabsTrigger value="__errors__" className="text-content px-3">
                  <Icon icon="fa-solid fa-triangle-exclamation" size="sm" />
                  Errors
                </TabsTrigger>
                <TabsTrigger value="__db__" className="text-content px-3">
                  <Icon icon="fa-solid fa-database" size="sm" />
                  DB
                </TabsTrigger>
                <div className="mx-2 my-2 w-px shrink-0 bg-border/50" aria-hidden />
                {containers.map(c => (
                  <TabsTrigger key={c.name} value={c.name} className="text-content px-3">
                    <span
                      className={`size-1.5 rounded-full shrink-0 ${c.running ? 'bg-status-online' : 'bg-muted-foreground/50'}`}
                    />
                    {c.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {isStatusMode && (
              <span className="text-label text-muted-foreground font-mono">
                {lastUpdate.toLocaleTimeString('zh-TW', { hour12: false })}
              </span>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={handleUnifiedRefresh}
              disabled={refreshBusy}
              aria-label="Refresh"
            >
              {refreshBusy ? (
                <Spinner />
              ) : (
                <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
              )}
            </Button>
          </div>
        </div>

        {/* Filter row — level pills + server-side search */}
        {isLogMode && (
          <div className="flex items-center gap-2 px-page py-1.5 border-b border-border/30 overflow-x-auto shrink-0">
            {LEVEL_FILTER_OPTS.map(lvl => (
              <button
                key={lvl}
                onClick={() => setLevelFilter(lvl)}
                className={`px-2.5 py-1 rounded text-sub font-mono transition-colors select-none shrink-0 ${levelPillClass(lvl, levelFilter === lvl)}`}
              >
                {lvl === 'WARNING' ? 'WARN' : lvl}
              </button>
            ))}
            {filtersActive && (
              <button
                onClick={() => {
                  setLevelFilter('INFO')
                  setSearch('')
                }}
                className="shrink-0 rounded px-2.5 py-1 text-sub font-mono text-muted-foreground/60 transition-colors select-none hover:bg-accent/50 hover:text-foreground"
              >
                ✕ 清除篩選
              </button>
            )}
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜尋…"
              className="ml-auto min-w-0 shrink rounded border border-border/40 bg-background px-2 py-1 font-mono text-sub outline-none focus:border-border"
            />
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

              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Icon
                      icon="fa-solid fa-bug"
                      size="sm"
                      wrapperClassName="text-muted-foreground"
                    />
                    <CardTitle className="text-card-title">前端錯誤</CardTitle>
                  </div>
                  <CardAction>
                    <button
                      onClick={() => setSelected('__errors__')}
                      className="text-label text-muted-foreground hover:text-foreground"
                    >
                      查看 →
                    </button>
                  </CardAction>
                </CardHeader>
                <CardContent>
                  <FieldRow
                    label="近 24 小時"
                    loading={errSummary === null}
                    offline={errSummary === 'error'}
                    value={
                      errSummary &&
                      errSummary !== 'error' && (
                        <span
                          className={
                            errSummary.total === 0 ? 'text-status-online' : 'text-status-warning'
                          }
                        >
                          {errSummary.total} 筆
                        </span>
                      )
                    }
                  />
                  <Separator className="opacity-40" />
                  <FieldRow
                    label="種類"
                    loading={errSummary === null}
                    offline={errSummary === 'error'}
                    value={errSummary && errSummary !== 'error' ? `${errSummary.kinds} 種` : null}
                  />
                </CardContent>
              </Card>
            </div>
          </div>
        ) : isDbMode ? (
          <DbConsole reloadNonce={reloadNonce} onLoadingChange={setPanelLoading} />
        ) : isErrorsMode ? (
          <ClientErrorsPanel
            onTraceRequestId={traceRequestId}
            reloadNonce={reloadNonce}
            onLoadingChange={setPanelLoading}
          />
        ) : (
          <div className="dark relative flex flex-col flex-1 min-h-0 min-w-0">
            <div
              ref={termRef}
              onScroll={handleScroll}
              className="flex-1 min-h-0 overflow-y-auto bg-background font-mono text-sub leading-6 py-2"
            >
              {loading && records.length === 0 ? (
                <div className="flex items-center gap-2 px-4 py-3 text-muted-foreground">
                  <Spinner className="size-3" />
                  <span>載入日誌中…</span>
                </div>
              ) : error ? (
                <div className="px-4 py-3 text-destructive">{error}</div>
              ) : records.length === 0 ? (
                <div className="px-4 py-3 text-muted-foreground">
                  {debouncedSearch || levelFilter !== 'ALL' ? '沒有符合條件的記錄' : '沒有日誌輸出'}
                </div>
              ) : (
                <div>
                  {records.map((rec, i) => {
                    const day = formatLogTime(rec.ts)?.date
                    const prevDay = i > 0 ? formatLogTime(records[i - 1].ts)?.date : undefined
                    return (
                      <Fragment key={i}>
                        {day && day !== prevDay && (
                          <div className="select-none px-3 py-1 text-sub text-muted-foreground/40">
                            ── {day} ──
                          </div>
                        )}
                        <LogRecordRow record={rec} index={i} />
                      </Fragment>
                    )
                  })}
                </div>
              )}
            </div>

            {!isFollowing && records.length > 0 && (
              <button
                onClick={jumpToLatest}
                className="absolute bottom-12 right-4 z-10 flex items-center gap-1.5 rounded-full border border-border/50 bg-accent px-3 py-1.5 text-sub font-mono text-accent-foreground shadow-lg transition-colors hover:bg-accent/80"
              >
                <Icon icon="fa-solid fa-arrow-down" size="xs" />
                最新
              </button>
            )}

            {/* Status bar */}
            <div className="flex items-center justify-between px-page lg:px-page-lg py-1.5 border-t border-border/20 bg-background shrink-0">
              <span className="font-mono text-sub text-muted-foreground">
                {records.length === 0 ? '—' : `${records.length} records · tail ${tail}`}
              </span>
              {isFollowing && (
                <span className="font-mono text-sub text-status-online flex items-center gap-1.5">
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
