import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getPublicCommands, type PublicChannelProfile, type PublicCommand } from '@/api/commands'
import { useTheme } from '@/components/theme-provider'
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
  Icon,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const ROLE_LABELS: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> =
  {
    everyone: { label: '所有人', variant: 'secondary' },
    subscriber: { label: '訂閱者', variant: 'outline' },
    vip: { label: 'VIP', variant: 'outline' },
    moderator: { label: '管理員', variant: 'default' },
    broadcaster: { label: '實況主', variant: 'default' },
  }

function nameSort(a: string, b: string): number {
  const aAscii = a.charCodeAt(0) < 128
  const bAscii = b.charCodeAt(0) < 128
  if (aAscii !== bAscii) return aAscii ? -1 : 1
  return a.localeCompare(b, 'zh-TW')
}

const TABS = [
  { value: 'builtin', label: '內建指令' },
  { value: 'custom', label: '自訂指令' },
  { value: 'trigger', label: '自動回應' },
] as const

type PublicSortKey = 'name' | 'min_role'
type SortDir = 'asc' | 'desc'

const ROLE_ORDER: Record<string, number> = {
  everyone: 0,
  subscriber: 1,
  vip: 2,
  moderator: 3,
  broadcaster: 4,
}

function SortableHead({
  children,
  className,
  sortKey: key,
  currentKey,
  dir,
  onSort,
}: {
  children: React.ReactNode
  className?: string
  sortKey: PublicSortKey
  currentKey: PublicSortKey
  dir: SortDir
  onSort: (key: PublicSortKey) => void
}) {
  const active = key === currentKey
  return (
    <TableHead className={className}>
      <button
        type="button"
        className="inline-flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
        onClick={() => onSort(key)}
      >
        {children}
        <Icon
          icon={
            active
              ? dir === 'asc'
                ? 'fa-solid fa-sort-up'
                : 'fa-solid fa-sort-down'
              : 'fa-solid fa-sort'
          }
          className={active ? 'text-foreground' : 'text-muted-foreground/50'}
          wrapperClassName="size-3"
        />
      </button>
    </TableHead>
  )
}

export default function PublicCommands() {
  const { username } = useParams<{ username: string }>()
  const { resolvedTheme, setTheme } = useTheme()
  const [commands, setCommands] = useState<PublicCommand[]>([])
  const [channel, setChannel] = useState<PublicChannelProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<PublicSortKey>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const toggleSort = (key: PublicSortKey) => {
    if (sortKey === key) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const sortedCommands = useMemo(() => {
    return (list: PublicCommand[]) => {
      return [...list].sort((a, b) => {
        let cmp = 0
        switch (sortKey) {
          case 'name':
            cmp = nameSort(a.name, b.name)
            break
          case 'min_role':
            cmp = (ROLE_ORDER[a.min_role] ?? 0) - (ROLE_ORDER[b.min_role] ?? 0)
            break
        }
        return sortDir === 'desc' ? -cmp : cmp
      })
    }
  }, [sortKey, sortDir])

  useEffect(() => {
    if (!username) return
    getPublicCommands(username)
      .then(data => {
        setChannel(data.channel)
        setCommands(data.commands)
      })
      .catch(() => setError('找不到該頻道或無法載入指令'))
      .finally(() => setLoading(false))
  }, [username])

  const displayName = channel?.display_name || username
  useDocumentTitle(channel ? `${displayName} Commands` : 'Commands')

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background px-page py-12">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-4"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>

      <div className="w-full max-w-2xl">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            載入中...
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-8 text-destructive">{error}</div>
        ) : (
          <Card className="rounded-2xl border shadow-xl">
            <CardHeader>
              <div className="flex flex-col items-center">
                <Avatar className="mb-4 h-24 w-24 border-4 border-primary shadow-lg">
                  <AvatarImage
                    src={channel?.profile_image_url ?? undefined}
                    alt={`${displayName} avatar`}
                  />
                  <AvatarFallback>
                    <img src="/images/Avatar.png" alt="fallback" className="h-full w-full" />
                  </AvatarFallback>
                </Avatar>
                <CardTitle className="text-center text-page-title">
                  {displayName} Commands
                </CardTitle>
                <a
                  href={`https://twitch.tv/${username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3"
                >
                  <Button variant="outline" size="sm">
                    <Icon icon="fa-brands fa-twitch" wrapperClassName="mr-1.5 size-3.5" />
                    前往頻道
                  </Button>
                </a>
              </div>
            </CardHeader>
            <CardContent>
              {commands.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  尚無指令
                </div>
              ) : (
                <Tabs defaultValue="builtin">
                  <TabsList>
                    {TABS.map(tab => (
                      <TabsTrigger key={tab.value} value={tab.value}>
                        {tab.label}
                        <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                          {commands.filter(c => c.command_type === tab.value).length}
                        </Badge>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {TABS.map(tab => {
                    const filtered = sortedCommands(
                      commands.filter(c => c.command_type === tab.value)
                    )
                    const isTrigger = tab.value === 'trigger'
                    return (
                      <TabsContent key={tab.value} value={tab.value}>
                        {filtered.length === 0 ? (
                          <div className="flex items-center justify-center py-8 text-muted-foreground">
                            尚無{tab.label}
                          </div>
                        ) : (
                          <div className="rounded-md border">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <SortableHead
                                    className="w-[25%]"
                                    sortKey="name"
                                    currentKey={sortKey}
                                    dir={sortDir}
                                    onSort={toggleSort}
                                  >
                                    {isTrigger ? '觸發詞' : '指令'}
                                  </SortableHead>
                                  <TableHead>說明</TableHead>
                                  <SortableHead
                                    className="w-[15%] text-center"
                                    sortKey="min_role"
                                    currentKey={sortKey}
                                    dir={sortDir}
                                    onSort={toggleSort}
                                  >
                                    權限
                                  </SortableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {filtered.map(cmd => {
                                  const role = ROLE_LABELS[cmd.min_role] ?? ROLE_LABELS.everyone
                                  return (
                                    <TableRow key={cmd.name}>
                                      <TableCell className="font-mono font-medium">
                                        {cmd.name}
                                      </TableCell>
                                      <TableCell className="text-muted-foreground">
                                        {cmd.description}
                                      </TableCell>
                                      <TableCell className="text-center">
                                        <Badge variant={role.variant} className="text-label">
                                          {role.label}
                                        </Badge>
                                      </TableCell>
                                    </TableRow>
                                  )
                                })}
                              </TableBody>
                            </Table>
                          </div>
                        )}
                      </TabsContent>
                    )
                  })}
                </Tabs>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
