import { Fragment, useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'

import {
  type CloudflareUsage,
  getClientErrorGroups,
  getCloudflareUsage,
  getContainerLogs,
  getLogContainers,
  getRateLimits,
  type LogContainer,
  type LogRecord,
  type RateLimits,
} from '@/api/admin'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
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
  formatLogTime,
  isApiContainer,
  LEVEL_FILTER_OPTS,
  type LevelFilter,
  levelPillClass,
} from './monitor/logParsers'
import { LogRecordRow } from './monitor/LogRecordRow'
import {
  cloudflareRatio,
  cloudflareSeverity,
  type Severity,
  worstSeverity,
} from './monitor/rateLimits'
import { CloudflareQuotaCard, RateLimitDigest, RateLimitSection } from './monitor/RateLimitViews'
import {
  CardLinkButton,
  EnvBadge,
  FieldRow,
  GaugeDetails,
  MonitorCard,
  StatusBadge,
  SummaryPill,
  VersionText,
} from './monitor/StatusCards'

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

type Mode = '__status__' | '__limits__' | '__errors__' | '__db__' | '__logs__'

const MODES: { value: Mode; label: string; icon: string }[] = [
  { value: '__status__', label: '總覽', icon: 'fa-solid fa-gauge' },
  { value: '__limits__', label: '限流', icon: 'fa-solid fa-gauge-high' },
  { value: '__errors__', label: '錯誤', icon: 'fa-solid fa-triangle-exclamation' },
  { value: '__db__', label: 'DB', icon: 'fa-solid fa-database' },
  { value: '__logs__', label: 'Logs', icon: 'fa-solid fa-terminal' },
]

const RATE_LIMIT_POLL_MS = 10_000
const CLOUDFLARE_POLL_MS = 60_000

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminMonitor() {
  useDocumentTitle('Monitor')

  const { guard, newToken } = useAbortableFetch()

  // ── Logs state ──────────────────────────────────────────────────────────────
  const [containers, setContainers] = useState<LogContainer[]>([])
  const [selected, setSelected] = useState<Mode>('__status__')
  // The container the Logs tab shows; defaults to the API's once the list loads.
  const [container, setContainer] = useState<string | null>(null)
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
      .then(cs =>
        guard(token, () => {
          setContainers(cs)
          setContainer(
            prev => prev ?? (cs.find(c => isApiContainer(c.name)) ?? cs[0])?.name ?? null
          )
        })
      )
      .catch(() => {})
  }, [guard, newToken])

  const query = { tail, level: levelFilter, q: debouncedSearch || undefined }

  useEffect(() => {
    if (selected !== '__logs__' || !container) return
    let cancelled = false
    dispatch({ type: 'start' })
    getContainerLogs(container, query)
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
  }, [selected, container, tail, levelFilter, debouncedSearch])

  const pollFetch = useCallback(async () => {
    if (selected !== '__logs__' || !container) return
    try {
      const data = await getContainerLogs(container, query)
      dispatch({ type: 'done', records: data.records })
    } catch {
      // silent — don't disrupt the view on transient poll failure
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, container, tail, levelFilter, debouncedSearch])

  const isDbMode = selected === '__db__'
  const isStatusMode = selected === '__status__'
  const isErrorsMode = selected === '__errors__'
  const isLimitsMode = selected === '__limits__'
  const isLogMode = selected === '__logs__'

  const filtersActive = levelFilter !== 'INFO' || search !== ''
  const refreshBusy = isLogMode ? loading : isStatusMode || isLimitsMode ? false : panelLoading

  usePolling({ fetchFn: pollFetch, intervalMs: 5_000, enabled: isLogMode, skipInitialCall: true })

  useEffect(() => {
    if (isFollowing && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight
    }
  }, [records, isFollowing])

  const handleRefresh = () => {
    if (!container) return
    const token = newToken()
    dispatch({ type: 'start' })
    getContainerLogs(container, query)
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

  /** Open the matching API log from the Errors tab. */
  const traceRequestId = useCallback(
    (requestId: string) => {
      const api = containers.find(c => isApiContainer(c.name))
      if (!api) return
      setSelected('__logs__')
      setContainer(api.name)
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

  // ── Rate limits + Cloudflare quota (總覽 digests and the 限流 tab) ──────────
  // undefined = not loaded yet; a failed load keeps the last data and flags it.
  const [rateLimits, setRateLimits] = useState<RateLimits | undefined>(undefined)
  const [rateLimitsFailed, setRateLimitsFailed] = useState(false)
  const [cfUsage, setCfUsage] = useState<CloudflareUsage | undefined>(undefined)
  const [cfFailed, setCfFailed] = useState(false)
  const showsLimits = isStatusMode || isLimitsMode

  const loadRateLimits = useCallback(async () => {
    try {
      setRateLimits(await getRateLimits())
      setRateLimitsFailed(false)
    } catch {
      setRateLimitsFailed(true)
    }
  }, [])
  const loadCfUsage = useCallback(async () => {
    try {
      setCfUsage(await getCloudflareUsage())
      setCfFailed(false)
    } catch {
      setCfFailed(true)
    }
  }, [])
  usePolling({ fetchFn: loadRateLimits, intervalMs: RATE_LIMIT_POLL_MS, enabled: showsLimits })
  usePolling({ fetchFn: loadCfUsage, intervalMs: CLOUDFLARE_POLL_MS, enabled: showsLimits })

  const refreshStatusAll = useCallback(() => {
    refreshStatus()
    loadErrSummary()
    void loadRateLimits()
    void loadCfUsage()
  }, [refreshStatus, loadErrSummary, loadRateLimits, loadCfUsage])

  /** One refresh button for every tab: live logs re-fetch, Status re-polls,
   *  DB / Errors panels reload via a bumped nonce. */
  const handleUnifiedRefresh = () => {
    if (isStatusMode || isLimitsMode) refreshStatusAll()
    else if (isLogMode) handleRefresh()
    else setReloadNonce(n => n + 1)
  }

  const services = useMemo(
    () => [
      {
        key: 'api' as const,
        name: 'API Server',
        icon: 'fa-solid fa-server',
        online: api.online,
        ready: undefined as boolean | undefined,
        dbPool: api.db_pool,
        caches: api.caches,
        memory: undefined,
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
        key: 'twitch' as const,
        name: 'Twitch Bot',
        icon: 'fa-brands fa-twitch',
        online: twitch.online,
        ready: twitch.ready,
        dbPool: twitch.db_pool,
        caches: twitch.caches,
        memory: twitch.memory,
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
        key: 'discord' as const,
        name: 'Discord Bot',
        icon: 'fa-brands fa-discord',
        online: discord.online,
        ready: discord.ready,
        dbPool: discord.db_pool,
        caches: discord.caches,
        memory: discord.memory,
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

  const limitsLevel: Severity = rateLimits
    ? worstSeverity([
        ...rateLimits.api,
        ...(rateLimits.twitch ?? []),
        ...(rateLimits.discord ?? []),
      ])
    : 'idle'

  return (
    <PageMain className="gap-0 p-0 lg:p-0 overflow-hidden">
      <div className="flex flex-col flex-1 min-h-0 min-w-0 overflow-hidden">
        {/* Tab bar — modes scroll on the left, refresh/clock pinned right */}
        <div className="flex items-stretch gap-2 px-page lg:px-page-lg border-b border-border/50 shrink-0">
          <div className="min-w-0 flex-1 overflow-x-auto">
            <Tabs
              value={selected}
              onValueChange={v => {
                setSelected(v as Mode)
                setLevelFilter('INFO')
                setPanelLoading(false)
                followRef.current = true
                setIsFollowing(true)
                if (v === '__status__' || v === '__limits__') refreshStatusAll()
              }}
            >
              <TabsList variant="line" className="h-11 bg-transparent gap-0">
                {MODES.map(m => (
                  <TabsTrigger key={m.value} value={m.value} className="text-content px-3">
                    <Icon icon={m.icon} size="sm" />
                    {m.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {(isStatusMode || isLimitsMode) && (
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
            <Select value={container ?? undefined} onValueChange={setContainer}>
              <SelectTrigger size="sm" className="w-40 shrink-0" aria-label="容器">
                <SelectValue placeholder="選擇容器" />
              </SelectTrigger>
              <SelectContent>
                {containers.map(c => (
                  <SelectItem key={c.name} value={c.name}>
                    <span
                      className={`size-1.5 rounded-full shrink-0 ${c.running ? 'bg-status-online' : 'bg-muted-foreground/50'}`}
                    />
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
            <div className="flex flex-wrap gap-element px-page pt-page lg:px-page-lg lg:pt-page-lg">
              <SummaryPill
                label="服務"
                value={`${services.filter(sv => sv.online).length}/${services.length} online`}
                level={services.every(sv => sv.online) ? 'ok' : 'hot'}
                loading={initialLoading}
              />
              <SummaryPill
                label="前端錯誤 24h"
                value={errSummary && errSummary !== 'error' ? `${errSummary.total} 筆` : '—'}
                level={errSummary === 'error' ? 'idle' : errSummary?.total ? 'warn' : 'ok'}
                loading={errSummary === null}
                onClick={() => setSelected('__errors__')}
              />
              <SummaryPill
                label="限流"
                value={limitsLevel === 'hot' ? '觸發中' : limitsLevel === 'warn' ? '繁忙' : '正常'}
                level={limitsLevel}
                loading={rateLimits === undefined && !rateLimitsFailed}
                onClick={() => setSelected('__limits__')}
              />
              <SummaryPill
                label="Cloudflare 今日"
                value={
                  cfUsage && cloudflareRatio(cfUsage) !== null
                    ? `${Math.round((cloudflareRatio(cfUsage) ?? 0) * 100)}%`
                    : cfUsage && !cfUsage.configured
                      ? '未設定'
                      : '—'
                }
                level={cfUsage ? cloudflareSeverity(cfUsage) : 'idle'}
                loading={cfUsage === undefined && !cfFailed}
                onClick={() => setSelected('__limits__')}
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-section p-page lg:p-page-lg">
              {services.map(service => (
                <MonitorCard
                  key={service.key}
                  icon={service.icon}
                  title={service.name}
                  loading={initialLoading}
                  badge={<StatusBadge online={service.online} ready={service.ready} />}
                >
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
                  {!initialLoading && service.online && (
                    <GaugeDetails
                      dbPool={service.dbPool}
                      caches={service.caches}
                      memory={service.memory}
                    />
                  )}
                  <RateLimitDigest
                    items={rateLimitsFailed ? null : rateLimits?.[service.key]}
                    offline={!initialLoading && !service.online}
                    onOpen={() => setSelected('__limits__')}
                  />
                </MonitorCard>
              ))}

              <MonitorCard
                icon="fa-solid fa-bug"
                title="前端錯誤"
                loading={errSummary === null}
                badge={
                  errSummary === 'error' ? (
                    <Badge variant="offline" className="gap-1.5">
                      <Icon icon="fa-solid fa-circle-xmark" size="xs" />
                      offline
                    </Badge>
                  ) : errSummary?.total === 0 ? (
                    <Badge variant="online" className="gap-1.5">
                      <Icon icon="fa-solid fa-circle-check" size="xs" />
                      clean
                    </Badge>
                  ) : (
                    <Badge variant="warning" className="gap-1.5">
                      <Icon icon="fa-solid fa-triangle-exclamation" size="xs" />
                      {errSummary?.total} 筆
                    </Badge>
                  )
                }
              >
                <FieldRow
                  label="近 24 小時"
                  loading={errSummary === null}
                  offline={errSummary === 'error'}
                  value={errSummary && errSummary !== 'error' ? `${errSummary.total} 筆` : null}
                />
                <Separator className="opacity-40" />
                <FieldRow
                  label="種類"
                  loading={errSummary === null}
                  offline={errSummary === 'error'}
                  value={errSummary && errSummary !== 'error' ? `${errSummary.kinds} 種` : null}
                />
                <CardLinkButton onClick={() => setSelected('__errors__')}>查看詳情</CardLinkButton>
              </MonitorCard>

              <CloudflareQuotaCard usage={cfUsage} failed={cfFailed} />
            </div>
          </div>
        ) : isLimitsMode ? (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-section p-page lg:p-page-lg">
              <CloudflareQuotaCard usage={cfUsage} failed={cfFailed} />
              <RateLimitSection
                title="API Server"
                icon="fa-solid fa-server"
                items={rateLimitsFailed ? null : rateLimits?.api}
              />
              <RateLimitSection
                title="Twitch Bot"
                icon="fa-brands fa-twitch"
                items={rateLimitsFailed ? null : rateLimits?.twitch}
              />
              <RateLimitSection
                title="Discord Bot"
                icon="fa-brands fa-discord"
                items={rateLimitsFailed ? null : rateLimits?.discord}
              />
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
