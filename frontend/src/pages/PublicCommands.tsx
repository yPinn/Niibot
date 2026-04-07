import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getPublicCommands, type PublicChannelProfile, type PublicCommand } from '@/api/commands'
import avatarFallback from '@/assets/images/Avatar.png'
import { SortableHead } from '@/components/SortableHead'
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
  Spinner,
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
import { useSortState } from '@/hooks/useSortState'
import { nameSort, ROLE_ORDER } from '@/lib/sort'

const ROLE_LABELS: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> =
  {
    everyone: { label: '所有人', variant: 'secondary' },
    subscriber: { label: '訂閱者', variant: 'outline' },
    vip: { label: 'VIP', variant: 'outline' },
    moderator: { label: '管理員', variant: 'default' },
    broadcaster: { label: '實況主', variant: 'default' },
  }

type BuiltinSortKey = 'name' | 'min_role'
type CustomSortKey = 'name' | 'kind' | 'min_role'

export default function PublicCommands() {
  const { username } = useParams<{ username: string }>()
  const { resolvedTheme, setTheme } = useTheme()
  const [commands, setCommands] = useState<PublicCommand[]>([])
  const [channel, setChannel] = useState<PublicChannelProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const builtinSort = useSortState<BuiltinSortKey>('name')
  const customSort = useSortState<CustomSortKey>('kind')

  const builtinRows = useMemo(() => {
    const { sortKey, sortDir } = builtinSort
    const list = commands.filter(c => c.command_type === 'builtin')
    return [...list].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'name') cmp = nameSort(a.name, b.name)
      else cmp = (ROLE_ORDER[a.min_role] ?? 0) - (ROLE_ORDER[b.min_role] ?? 0)
      return sortDir === 'desc' ? -cmp : cmp
    })
  }, [commands, builtinSort])

  const customRows = useMemo(() => {
    const { sortKey, sortDir } = customSort
    const list = commands.filter(c => c.command_type === 'custom' || c.command_type === 'trigger')
    return [...list].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'name') cmp = nameSort(a.name, b.name)
      else if (sortKey === 'kind') {
        const kindCmp =
          (a.command_type === 'custom' ? 0 : 1) - (b.command_type === 'custom' ? 0 : 1)
        cmp = kindCmp !== 0 ? kindCmp : nameSort(a.name, b.name)
      } else cmp = (ROLE_ORDER[a.min_role] ?? 0) - (ROLE_ORDER[b.min_role] ?? 0)
      return sortDir === 'desc' ? -cmp : cmp
    })
  }, [commands, customSort])

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
      <Button variant="ghost" size="icon" className="absolute left-4 top-4" asChild>
        <Link to="/">
          <Icon icon="fa-solid fa-house" wrapperClassName="" />
        </Link>
      </Button>

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
          <div className="flex items-center justify-center py-empty">
            <Spinner className="size-8 text-primary" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-empty text-destructive">{error}</div>
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
                                currentKey={builtinSort.sortKey}
                                dir={builtinSort.sortDir}
                                onSort={builtinSort.toggleSort}
                              >
                                指令
                              </SortableHead>
                              <TableHead>說明</TableHead>
                              <SortableHead
                                className="w-[15%] text-center"
                                sortKey="min_role"
                                currentKey={builtinSort.sortKey}
                                dir={builtinSort.sortDir}
                                onSort={builtinSort.toggleSort}
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
                                currentKey={customSort.sortKey}
                                dir={customSort.sortDir}
                                onSort={customSort.toggleSort}
                              >
                                名稱
                              </SortableHead>
                              <SortableHead
                                className="w-[12%]"
                                sortKey="kind"
                                currentKey={customSort.sortKey}
                                dir={customSort.sortDir}
                                onSort={customSort.toggleSort}
                              >
                                類型
                              </SortableHead>
                              <TableHead>說明</TableHead>
                              <SortableHead
                                className="w-[15%] text-center"
                                sortKey="min_role"
                                currentKey={customSort.sortKey}
                                dir={customSort.sortDir}
                                onSort={customSort.toggleSort}
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
