import { useMemo } from 'react'

import { Icon } from '@/components/ui'
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

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-baseline gap-4 py-1.5 border-b border-border/30 last:border-0">
      <span className="text-sub text-muted-foreground shrink-0">{label}</span>
      <span className="font-mono text-sub text-right">{value}</span>
    </div>
  )
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

export default function SystemStatus() {
  useDocumentTitle('System Status')
  const { twitch, discord, api, lastUpdate, refresh } = useServiceStatus()

  const services = useMemo(
    () => [
      {
        key: 'api',
        name: 'API Server',
        icon: 'fa-solid fa-server',
        online: api.online,
        ready: undefined,
        rows: [
          { label: 'version', value: api.version ?? '—' },
          { label: 'commit', value: <CommitLink commit={api.git_commit} /> },
          { label: 'env', value: <EnvBadge env={api.environment} /> },
          { label: 'started', value: formatStartedAt(api.started_at) },
          { label: 'uptime', value: formatUptime(api.uptime_seconds) },
          {
            label: 'database',
            value:
              api.db_connected === undefined ? (
                '—'
              ) : (
                <span className={api.db_connected ? 'text-status-online' : 'text-status-offline'}>
                  {api.db_connected ? 'connected' : 'disconnected'}
                </span>
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
        rows: [
          { label: 'version', value: twitch.version ?? '—' },
          { label: 'commit', value: <CommitLink commit={twitch.git_commit} /> },
          { label: 'started', value: formatStartedAt(twitch.started_at) },
          { label: 'uptime', value: formatUptime(twitch.uptime_seconds) },
          { label: 'bot_id', value: twitch.bot_id ?? '—' },
          { label: 'channels', value: twitch.connected_channels ?? '—' },
        ],
      },
      {
        key: 'discord',
        name: 'Discord Bot',
        icon: 'fa-brands fa-discord',
        online: discord.online,
        ready: discord.ready,
        rows: [
          { label: 'version', value: discord.version ?? '—' },
          { label: 'commit', value: <CommitLink commit={discord.git_commit} /> },
          { label: 'started', value: formatStartedAt(discord.started_at) },
          { label: 'uptime', value: formatUptime(discord.uptime_seconds) },
          { label: 'bot_id', value: discord.bot_id ?? '—' },
          { label: 'guilds', value: discord.guilds ?? '—' },
          {
            label: 'ws_latency',
            value: discord.ws_latency_ms !== undefined ? `${discord.ws_latency_ms}ms` : '—',
          },
        ],
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
        <button
          onClick={refresh}
          className="p-2 hover:bg-accent rounded-md transition-colors active:scale-95"
          title="Refresh now"
        >
          <Icon icon="fa-solid fa-rotate" className="w-4 h-4 text-muted-foreground" />
        </button>
      </div>

      <div className="grid gap-section md:grid-cols-2 lg:grid-cols-3">
        {services.map(service => (
          <div key={service.key} className="bg-card border rounded-lg p-card shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Icon icon={service.icon} className="w-4 h-4 text-muted-foreground" />
                <h3 className="font-semibold text-card-title">{service.name}</h3>
              </div>
              <StatusBadge online={service.online} ready={service.ready} />
            </div>

            <div className="border-t border-border/40 pt-3">
              {service.online ? (
                service.rows.map(row => <Row key={row.label} label={row.label} value={row.value} />)
              ) : (
                <p className="text-sub text-muted-foreground font-mono py-2">service unreachable</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </main>
  )
}
