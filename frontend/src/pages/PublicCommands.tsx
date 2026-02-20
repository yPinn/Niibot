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

const ROLE_ORDER: Record<string, number> = {
  everyone: 0,
  subscriber: 1,
  vip: 2,
  moderator: 3,
  broadcaster: 4,
}

function nameSort(a: string, b: string): number {
  const aAscii = a.charCodeAt(0) < 128
  const bAscii = b.charCodeAt(0) < 128
  if (aAscii !== bAscii) return aAscii ? -1 : 1
  return a.localeCompare(b, 'zh-TW')
}

type BuiltinSortKey = 'name' | 'min_role'
type CustomSortKey = 'name' | 'kind' | 'min_role'
type SortDir = 'asc' | 'desc'

function SortableHead<K extends string>({
  children,
  className,
  sortKey: key,
  currentKey,
  dir,
  onSort,
}: {
  children: React.ReactNode
  className?: string
  sortKey: K
  currentKey: K
  dir: SortDir
  onSort: (key: K) => void
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

  const [builtinSortKey, setBuiltinSortKey] = useState<BuiltinSortKey>('name')
  const [builtinSortDir, setBuiltinSortDir] = useState<SortDir>('asc')
  const [customSortKey, setCustomSortKey] = useState<CustomSortKey>('name')
  const [customSortDir, setCustomSortDir] = useState<SortDir>('asc')

  const toggleBuiltinSort = (key: BuiltinSortKey) => {
    if (builtinSortKey === key) {
      setBuiltinSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setBuiltinSortKey(key)
      setBuiltinSortDir('asc')
    }
  }

  const toggleCustomSort = (key: CustomSortKey) => {
    if (customSortKey === key) {
      setCustomSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setCustomSortKey(key)
      setCustomSortDir('asc')
    }
  }

  const builtinRows = useMemo(() => {
    const list = commands.filter(c => c.command_type === 'builtin')
    return [...list].sort((a, b) => {
      let cmp = 0
      if (builtinSortKey === 'name') cmp = nameSort(a.name, b.name)
      else cmp = (ROLE_ORDER[a.min_role] ?? 0) - (ROLE_ORDER[b.min_role] ?? 0)
      return builtinSortDir === 'desc' ? -cmp : cmp
    })
  }, [commands, builtinSortKey, builtinSortDir])

  const customRows = useMemo(() => {
    const list = commands.filter(c => c.command_type === 'custom' || c.command_type === 'trigger')
    return [...list].sort((a, b) => {
      let cmp = 0
      if (customSortKey === 'name') cmp = nameSort(a.name, b.name)
      else if (customSortKey === 'kind')
        cmp = (a.command_type === 'custom' ? 0 : 1) - (b.command_type === 'custom' ? 0 : 1)
      else cmp = (ROLE_ORDER[a.min_role] ?? 0) - (ROLE_ORDER[b.min_role] ?? 0)
      return customSortDir === 'desc' ? -cmp : cmp
    })
  }, [commands, customSortKey, customSortDir])

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
  useDocumentTitle(channel ? `${displayName}'s Commands` : 'Commands')

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
                <a
                  href={`https://twitch.tv/${username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group relative mb-4"
                >
                  <Avatar className="h-24 w-24 border-4 border-primary shadow-lg">
                    <AvatarImage
                      src={channel?.profile_image_url ?? undefined}
                      alt={`${displayName} avatar`}
                    />
                    <AvatarFallback>
                      <img src="/images/Avatar.png" alt="fallback" className="h-full w-full" />
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
                    <TabsTrigger value="builtin">
                      內建
                      <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                        {commands.filter(c => c.command_type === 'builtin').length}
                      </Badge>
                    </TabsTrigger>
                    <TabsTrigger value="custom">
                      自訂
                      <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                        {
                          commands.filter(
                            c => c.command_type === 'custom' || c.command_type === 'trigger'
                          ).length
                        }
                      </Badge>
                    </TabsTrigger>
                  </TabsList>

                  {/* ── Builtin Tab ── */}
                  <TabsContent value="builtin">
                    {builtinRows.length === 0 ? (
                      <div className="flex items-center justify-center py-8 text-muted-foreground">
                        尚無內建指令
                      </div>
                    ) : (
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <SortableHead
                                className="w-[25%]"
                                sortKey="name"
                                currentKey={builtinSortKey}
                                dir={builtinSortDir}
                                onSort={toggleBuiltinSort}
                              >
                                指令
                              </SortableHead>
                              <TableHead>說明</TableHead>
                              <SortableHead
                                className="w-[15%] text-center"
                                sortKey="min_role"
                                currentKey={builtinSortKey}
                                dir={builtinSortDir}
                                onSort={toggleBuiltinSort}
                              >
                                權限
                              </SortableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {builtinRows.map(cmd => {
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

                  {/* ── Custom Tab (commands + triggers mixed) ── */}
                  <TabsContent value="custom">
                    {customRows.length === 0 ? (
                      <div className="flex items-center justify-center py-8 text-muted-foreground">
                        尚無自訂指令或自動回應
                      </div>
                    ) : (
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <SortableHead
                                className="w-[25%]"
                                sortKey="name"
                                currentKey={customSortKey}
                                dir={customSortDir}
                                onSort={toggleCustomSort}
                              >
                                名稱
                              </SortableHead>
                              <SortableHead
                                className="w-[12%]"
                                sortKey="kind"
                                currentKey={customSortKey}
                                dir={customSortDir}
                                onSort={toggleCustomSort}
                              >
                                類型
                              </SortableHead>
                              <TableHead>說明</TableHead>
                              <SortableHead
                                className="w-[15%] text-center"
                                sortKey="min_role"
                                currentKey={customSortKey}
                                dir={customSortDir}
                                onSort={toggleCustomSort}
                              >
                                權限
                              </SortableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {customRows.map(cmd => {
                              const role = ROLE_LABELS[cmd.min_role] ?? ROLE_LABELS.everyone
                              return (
                                <TableRow key={cmd.name}>
                                  <TableCell className="font-mono font-medium">
                                    {cmd.name}
                                  </TableCell>
                                  <TableCell>
                                    {cmd.command_type === 'custom' ? (
                                      <Badge variant="default">指令</Badge>
                                    ) : (
                                      <Badge variant="secondary">觸發</Badge>
                                    )}
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
                </Tabs>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
