import { useMemo } from 'react'

import { Button, Card, CardContent, Icon, Skeleton } from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const GITHUB_COMMIT_BASE = 'https://github.com/yPinn/Niibot/commit/'

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

function StatusBadge({ online, ready }: { online: boolean; ready?: boolean }) {
  if (!online) {
    return (
      <span className="inline-flex items-center gap-1.5 text-label font-medium text-status-offline">
        <Icon icon="fa-solid fa-circle-xmark" className="w-3 h-3" />
        offline
      </span>
    )
  }
  if (ready === false) {
    return (
      <span className="inline-flex items-center gap-1.5 text-label font-medium text-status-loading">
        <Icon icon="fa-solid fa-circle-half-stroke" className="w-3 h-3" />
        starting
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-label font-medium text-status-online">
      <Icon icon="fa-solid fa-circle-check" className="w-3 h-3" />
      online
    </span>
  )
}

function EnvBadge({ env }: { env?: string }) {
  if (!env) return <span className="font-mono text-label text-muted-foreground">—</span>
  const color =
    env === 'production'
      ? 'bg-status-live/10 text-status-live'
      : env === 'staging'
        ? 'bg-status-loading/10 text-status-loading'
        : 'bg-status-info/10 text-status-info'
  return (
    <span className={`px-1.5 py-0.5 rounded text-label font-mono font-medium ${color}`}>{env}</span>
  )
}

function CommitLink({ commit }: { commit?: string }) {
  if (!commit || commit === 'unknown') {
    return <span className="font-mono text-muted-foreground">unknown</span>
  }
  return (
    <a
      href={`${GITHUB_COMMIT_BASE}${commit}`}
      target="_blank"
      rel="noopener noreferrer"
      className="font-mono text-status-info hover:underline"
    >
      {commit.slice(0, 7)}
    </a>
  )
}

const DASH = <span className="text-muted-foreground/40">—</span>

export default function SystemStatus() {
  useDocumentTitle('System Status')
  const { twitch, discord, api, lastUpdate, initialLoading, refresh } = useServiceStatus()

  const serviceHeaders = useMemo(
    () => [
      {
        key: 'api',
        name: 'API Server',
        icon: 'fa-solid fa-server',
        online: api.online,
        ready: undefined as boolean | undefined,
      },
      {
        key: 'twitch',
        name: 'Twitch Bot',
        icon: 'fa-brands fa-twitch',
        online: twitch.online,
        ready: twitch.ready,
      },
      {
        key: 'discord',
        name: 'Discord Bot',
        icon: 'fa-brands fa-discord',
        online: discord.online,
        ready: discord.ready,
      },
    ],
    [twitch, discord, api]
  )

  const fieldRows = useMemo(
    () => [
      {
        label: 'version',
        values: [
          api.version ?? '—',
          twitch.version ?? '—',
          discord.version ?? '—',
        ] as React.ReactNode[],
      },
      {
        label: 'commit',
        values: [
          <CommitLink key="api" commit={api.git_commit} />,
          <CommitLink key="twitch" commit={twitch.git_commit} />,
          <CommitLink key="discord" commit={discord.git_commit} />,
        ] as React.ReactNode[],
      },
      {
        label: 'env',
        values: [
          <EnvBadge key="api" env={api.environment} />,
          null,
          null,
        ] as (React.ReactNode | null)[],
      },
      {
        label: 'started',
        values: [
          formatStartedAt(api.started_at),
          formatStartedAt(twitch.started_at),
          formatStartedAt(discord.started_at),
        ] as React.ReactNode[],
      },
      {
        label: 'uptime',
        values: [
          formatUptime(api.uptime_seconds),
          formatUptime(twitch.uptime_seconds),
          formatUptime(discord.uptime_seconds),
        ] as React.ReactNode[],
      },
      {
        label: 'database',
        values: [
          api.db_connected === undefined ? null : (
            <span
              key="api"
              className={api.db_connected ? 'text-status-online' : 'text-status-offline'}
            >
              {api.db_connected ? 'connected' : 'disconnected'}
            </span>
          ),
          null,
          null,
        ] as (React.ReactNode | null)[],
      },
      {
        label: 'bot_id',
        values: [null, twitch.bot_id ?? '—', discord.bot_id ?? '—'] as (React.ReactNode | null)[],
      },
      {
        label: 'channels',
        values: [null, twitch.connected_channels ?? '—', null] as (React.ReactNode | null)[],
      },
      {
        label: 'guilds',
        values: [null, null, discord.guilds ?? '—'] as (React.ReactNode | null)[],
      },
      {
        label: 'ws_latency',
        values: [
          null,
          null,
          discord.ws_latency_ms !== undefined ? `${discord.ws_latency_ms}ms` : null,
        ] as (React.ReactNode | null)[],
      },
    ],
    [twitch, discord, api]
  )

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:gap-card lg:p-page-lg">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-page-title font-bold">System Status</h1>
          <p className="text-sub text-muted-foreground font-mono mt-1">
            polled every 30s · last update{' '}
            {lastUpdate.toLocaleTimeString('zh-TW', { hour12: false })}
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={refresh} aria-label="Refresh now">
          <Icon icon="fa-solid fa-rotate" className="w-4 h-4 text-muted-foreground" />
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-hidden">
          <div className="grid grid-cols-[7rem_1fr_1fr_1fr]">
            {/* ── Service header row ── */}
            <div className="px-4 py-3 border-b border-border/40" />
            {serviceHeaders.map(s => (
              <div
                key={s.key}
                className="px-4 py-3 border-b border-l border-border/40 flex flex-col gap-1.5"
              >
                <div className="flex items-center gap-2">
                  <Icon icon={s.icon} className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span className="text-sub font-semibold truncate">{s.name}</span>
                </div>
                {initialLoading ? (
                  <Skeleton className="h-4 w-14" />
                ) : (
                  <StatusBadge online={s.online} ready={s.ready} />
                )}
              </div>
            ))}

            {/* ── Field rows ── */}
            {fieldRows.map((field, rowIdx) => {
              const isLast = rowIdx === fieldRows.length - 1
              const borderB = isLast ? '' : 'border-b border-border/30'
              return (
                <div key={field.label} className="contents">
                  {/* Label cell */}
                  <div className={`px-4 py-1.5 flex items-center ${borderB}`}>
                    <span className="text-sub text-muted-foreground">{field.label}</span>
                  </div>
                  {/* Value cells */}
                  {field.values.map((val, colIdx) => {
                    const offline = !serviceHeaders[colIdx].online
                    return (
                      <div
                        key={colIdx}
                        className={`px-4 py-1.5 border-l border-border/20 font-mono text-sub flex items-center ${borderB}`}
                      >
                        {initialLoading ? (
                          <Skeleton className="h-4 w-20" />
                        ) : offline ? (
                          DASH
                        ) : val !== null ? (
                          val
                        ) : (
                          DASH
                        )}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </main>
  )
}
