import { useMemo } from 'react'

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
  Stagger,
  StaggerItem,
} from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

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

const DASH = <span className="text-muted-foreground/40">—</span>

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

export default function SystemStatus() {
  useDocumentTitle('System Status')
  const { twitch, discord, api, lastUpdate, initialLoading, refresh } = useServiceStatus()

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
          ...(discord.ws_latency_ms !== undefined
            ? [{ label: 'ws latency', value: `${discord.ws_latency_ms}ms` }]
            : []),
        ],
      },
    ],
    [twitch, discord, api]
  )

  return (
    <PageMain className="lg:gap-card">
      <SlideUp className="flex items-center justify-between">
        <div>
          <h1 className="text-page-title font-bold">System Status</h1>
          <p className="text-label text-muted-foreground font-mono mt-1">
            polled every 30s · last updated{' '}
            {lastUpdate.toLocaleTimeString('zh-TW', { hour12: false })}
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={refresh} aria-label="Refresh">
          <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
        </Button>
      </SlideUp>

      <Stagger className="grid gap-section grid-cols-1 md:grid-cols-3" delayChildren={0.05}>
        {services.map(service => (
          <StaggerItem key={service.key}>
            <Card>
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
          </StaggerItem>
        ))}
      </Stagger>
    </PageMain>
  )
}
