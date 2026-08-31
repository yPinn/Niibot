import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getPublicCommands, type PublicChannelProfile, type PublicCommand } from '@/api/commands'
import avatarFallback from '@/assets/images/Avatar.png'
import { useTheme } from '@/components/layout/theme-provider'
import { EmptyState, FadeIn, Icon } from '@/components/primitives'
import { TableShell } from '@/components/TableShell'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

type ViewerRole = 'everyone' | 'subscriber' | 'vip'

const VIEWER_ROLE_GROUPS: ReadonlyArray<{
  role: ViewerRole
  label: string
  description: string
}> = [
  { role: 'everyone', label: 'For everyone', description: '所有觀眾都能使用' },
  { role: 'subscriber', label: 'Subscribers', description: '最低權限為 Subscriber' },
  { role: 'vip', label: 'VIPs', description: '最低權限為 VIP' },
]

const COMMAND_TYPE_LABELS: Record<PublicCommand['command_type'], string> = {
  builtin: '內建',
  custom: '自訂',
  trigger: '自動回應',
}

export default function PublicCommands() {
  const { username } = useParams<{ username: string }>()
  const { resolvedTheme, setTheme } = useTheme()
  const [commands, setCommands] = useState<PublicCommand[]>([])
  const [channel, setChannel] = useState<PublicChannelProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const commandGroups = useMemo(
    () =>
      VIEWER_ROLE_GROUPS.map(group => ({
        ...group,
        commands: commands.filter(command => command.min_role === group.role),
      })).filter(group => group.commands.length > 0),
    [commands]
  )

  useEffect(() => {
    if (!username) return
    let cancelled = false
    getPublicCommands(username)
      .then(data => {
        if (!cancelled) {
          setChannel(data.channel)
          setCommands(data.commands)
        }
      })
      .catch(() => {
        if (!cancelled) setError('找不到該頻道或無法載入指令')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [username])

  const displayName = channel?.display_name ?? username ?? ''
  useDocumentTitle(channel ? `${displayName}'s Commands` : 'Commands')

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background px-page py-12">
      <Button variant="ghost" size="icon" className="absolute left-4 top-4" asChild>
        <Link to="/" aria-label="返回首頁">
          <Icon icon="fa-solid fa-house" wrapperClassName="" />
        </Link>
      </Button>

      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-4"
        aria-label="切換顯示主題"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>

      <div className="w-full max-w-3xl">
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="mx-auto h-24 w-24 rounded-full" />
            <Skeleton className="mx-auto h-6 w-40" />
            <div className="pt-2">
              <TableSkeletonRows count={5} />
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-empty text-destructive">{error}</div>
        ) : (
          <FadeIn>
            <Card className="rounded-2xl border shadow-xl">
              <CardHeader>
                <div className="flex flex-col items-center">
                  <a
                    href={`https://twitch.tv/${username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group relative mb-4"
                    aria-label={`前往 ${displayName} 的 Twitch 頻道`}
                  >
                    <Avatar className="h-24 w-24 border-4 border-primary shadow-lg">
                      <AvatarImage
                        src={channel?.profile_image_url ?? undefined}
                        alt={`${displayName} avatar`}
                      />
                      <AvatarFallback>
                        <img src={avatarFallback} alt="預設頭像" className="h-full w-full" />
                      </AvatarFallback>
                    </Avatar>
                    <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
                      <Icon
                        icon="fa-brands fa-twitch"
                        className="text-white"
                        wrapperClassName="size-8"
                      />
                    </div>
                  </a>
                  <CardTitle className="text-center text-page-title">
                    {displayName}'s Commands
                  </CardTitle>
                  <p className="mt-2 max-w-lg text-center text-sub text-muted-foreground">
                    依 Twitch 使用身分整理目前已啟用、可由觀眾使用的指令。
                  </p>
                </div>
              </CardHeader>

              <CardContent className="space-y-section">
                {commandGroups.length === 0 ? (
                  <EmptyState
                    icon="fa-solid fa-terminal"
                    title="尚無公開指令"
                    description="此實況主尚未啟用觀眾可用的指令"
                  />
                ) : (
                  commandGroups.map(group => {
                    const headingId = `commands-${group.role}`
                    return (
                      <section key={group.role} aria-labelledby={headingId} className="space-y-2">
                        <div className="flex items-end justify-between gap-3">
                          <div>
                            <h2 id={headingId} className="font-semibold">
                              {group.label}
                            </h2>
                            <p className="text-label text-muted-foreground">{group.description}</p>
                          </div>
                          <span className="text-label tabular-nums text-muted-foreground">
                            {group.commands.length} 個
                          </span>
                        </div>

                        <TableShell fixed={false}>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="w-[28%]">指令</TableHead>
                              <TableHead className="w-[18%]">類型</TableHead>
                              <TableHead>說明</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {group.commands.map(command => (
                              <TableRow key={`${command.command_type}:${command.name}`}>
                                <TableCell className="font-mono font-medium">
                                  {command.name}
                                </TableCell>
                                <TableCell>
                                  <Badge
                                    variant={
                                      command.command_type === 'builtin' ? 'secondary' : 'outline'
                                    }
                                    className="text-label"
                                  >
                                    {COMMAND_TYPE_LABELS[command.command_type]}
                                  </Badge>
                                </TableCell>
                                <TableCell className="whitespace-normal text-sub text-muted-foreground">
                                  {command.description}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </TableShell>
                      </section>
                    )
                  })
                )}
              </CardContent>
            </Card>
          </FadeIn>
        )}
      </div>
    </div>
  )
}
