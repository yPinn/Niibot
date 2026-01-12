import { useCallback, useEffect, useState } from 'react'

import { type ComponentInfo, getComponents } from '@/api'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Icon } from '@/components/ui/icon'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export default function Commands() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedPlatform, setSelectedPlatform] = useState<'all' | 'discord' | 'twitch'>('all')
  const [components, setComponents] = useState<{
    discord: ComponentInfo[]
    twitch: ComponentInfo[]
  }>({ discord: [], twitch: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchComponents = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getComponents()
      setComponents({
        discord: data.discord,
        twitch: data.twitch,
      })
      setError(null)
    } catch (err) {
      console.error('Failed to fetch components:', err)
      setError('無法載入組件資訊')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchComponents()
  }, [fetchComponents])

  const allCommands = [
    ...components.discord.flatMap(comp =>
      comp.commands.map(cmd => ({ ...cmd, component: comp.name }))
    ),
    ...components.twitch.flatMap(comp =>
      comp.commands.map(cmd => ({ ...cmd, component: comp.name }))
    ),
  ]

  const filteredCommands = allCommands.filter(
    cmd =>
      cmd.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      cmd.component.toLowerCase().includes(searchQuery.toLowerCase()) ||
      cmd.description?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getPlatformBadge = (platform: 'discord' | 'twitch') => {
    const config = {
      discord: {
        color: 'bg-indigo-500/10 text-indigo-500',
        icon: 'fa-brands fa-discord',
      },
      twitch: {
        color: 'bg-purple-500/10 text-purple-500',
        icon: 'fa-brands fa-twitch',
      },
    }
    return (
      <Badge variant="outline" className={config[platform].color}>
        <Icon icon={config[platform].icon} wrapperClassName="mr-1 size-3" />
        {platform.charAt(0).toUpperCase() + platform.slice(1)}
      </Badge>
    )
  }

  if (loading) {
    return <LoadingSpinner fullScreen text="載入中..." />
  }

  if (error) {
    return (
      <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-8">
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      </main>
    )
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Bot Components</h1>
          <p className="text-muted-foreground">瀏覽所有 Discord 和 Twitch 機器人組件及指令</p>
        </div>
        <div className="flex gap-2">
          <Badge variant="outline">Discord: {components.discord.length}</Badge>
          <Badge variant="outline">Twitch: {components.twitch.length}</Badge>
        </div>
      </div>

      {/* Platform Selector */}
      <Card>
        <CardContent className="p-4 py-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">選擇平台：</span>
            <div className="flex gap-2">
              <Badge
                variant={selectedPlatform === 'all' ? 'default' : 'outline'}
                className="cursor-pointer"
                onClick={() => setSelectedPlatform('all')}
              >
                全部
              </Badge>
              <Badge
                variant={selectedPlatform === 'discord' ? 'default' : 'outline'}
                className="cursor-pointer bg-indigo-500/10 text-indigo-500 hover:bg-indigo-500/20"
                onClick={() => setSelectedPlatform('discord')}
              >
                <Icon icon="fa-brands fa-discord" wrapperClassName="mr-1 size-3" />
                Discord
              </Badge>
              <Badge
                variant={selectedPlatform === 'twitch' ? 'default' : 'outline'}
                className="cursor-pointer bg-purple-500/10 text-purple-500 hover:bg-purple-500/20"
                onClick={() => setSelectedPlatform('twitch')}
              >
                <Icon icon="fa-brands fa-twitch" wrapperClassName="mr-1 size-3" />
                Twitch
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Discord Components */}
      {(selectedPlatform === 'all' || selectedPlatform === 'discord') && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Icon icon="fa-brands fa-discord" wrapperClassName="size-5 text-indigo-500" />
              Discord Components ({components.discord.length})
            </CardTitle>
            <CardDescription>Discord 機器人的 Cogs 組件</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {components.discord.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">沒有找到 Discord 組件</p>
            ) : (
              components.discord.map(comp => (
                <Collapsible key={comp.name}>
                  <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border p-4 hover:bg-accent">
                    <div className="flex flex-col items-start gap-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{comp.name}</span>
                        <Badge variant="secondary">{comp.commands.length} 指令</Badge>
                      </div>
                      {comp.description && (
                        <span className="text-sm text-muted-foreground">{comp.description}</span>
                      )}
                    </div>
                    <Icon icon="fa-solid fa-chevron-down" wrapperClassName="size-4" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-2">
                    <div className="rounded-md border ml-4">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>指令名稱</TableHead>
                            <TableHead>別名</TableHead>
                            <TableHead>描述</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {comp.commands.map((cmd, idx) => (
                            <TableRow key={`${comp.name}-${cmd.name}-${idx}`}>
                              <TableCell className="font-mono font-medium">{cmd.name}</TableCell>
                              <TableCell>
                                {cmd.aliases.length > 0 ? (
                                  <div className="flex gap-1 flex-wrap">
                                    {cmd.aliases.map(alias => (
                                      <Badge key={alias} variant="outline" className="font-mono">
                                        {alias}
                                      </Badge>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground text-sm">無</span>
                                )}
                              </TableCell>
                              <TableCell className="max-w-md">
                                {cmd.description || (
                                  <span className="text-muted-foreground text-sm">無描述</span>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              ))
            )}
          </CardContent>
        </Card>
      )}

      {/* Twitch Components */}
      {(selectedPlatform === 'all' || selectedPlatform === 'twitch') && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Icon icon="fa-brands fa-twitch" wrapperClassName="size-5 text-purple-500" />
              Twitch Components ({components.twitch.length})
            </CardTitle>
            <CardDescription>Twitch 機器人的 Components 組件</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {components.twitch.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">沒有找到 Twitch 組件</p>
            ) : (
              components.twitch.map(comp => (
                <Collapsible key={comp.name}>
                  <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border p-4 hover:bg-accent">
                    <div className="flex flex-col items-start gap-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{comp.name}</span>
                        <Badge variant="secondary">{comp.commands.length} 指令</Badge>
                      </div>
                      {comp.description && (
                        <span className="text-sm text-muted-foreground">{comp.description}</span>
                      )}
                    </div>
                    <Icon icon="fa-solid fa-chevron-down" wrapperClassName="size-4" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-2">
                    <div className="rounded-md border ml-4">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>指令名稱</TableHead>
                            <TableHead>別名</TableHead>
                            <TableHead>描述</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {comp.commands.map((cmd, idx) => (
                            <TableRow key={`${comp.name}-${cmd.name}-${idx}`}>
                              <TableCell className="font-mono font-medium">{cmd.name}</TableCell>
                              <TableCell>
                                {cmd.aliases.length > 0 ? (
                                  <div className="flex gap-1 flex-wrap">
                                    {cmd.aliases.map(alias => (
                                      <Badge key={alias} variant="outline" className="font-mono">
                                        {alias}
                                      </Badge>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground text-sm">無</span>
                                )}
                              </TableCell>
                              <TableCell className="max-w-md">
                                {cmd.description || (
                                  <span className="text-muted-foreground text-sm">無描述</span>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              ))
            )}
          </CardContent>
        </Card>
      )}

      {/* All Commands Search */}
      <Card>
        <CardHeader>
          <CardTitle>搜尋所有指令</CardTitle>
          <CardDescription>快速搜尋所有平台的指令</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <div className="relative">
              <Icon
                icon="fa-solid fa-magnifying-glass"
                wrapperClassName="absolute left-2 top-2.5 size-4 text-muted-foreground"
              />
              <Input
                placeholder="搜尋指令名稱、組件或描述..."
                className="pl-8"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>平台</TableHead>
                  <TableHead>組件</TableHead>
                  <TableHead>指令名稱</TableHead>
                  <TableHead>別名</TableHead>
                  <TableHead>描述</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCommands.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      {searchQuery ? '沒有找到符合的指令' : '請輸入關鍵字搜尋'}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredCommands.map((command, idx) => (
                    <TableRow key={`${command.component}-${command.name}-${idx}`}>
                      <TableCell>{getPlatformBadge(command.platform)}</TableCell>
                      <TableCell className="font-medium">{command.component}</TableCell>
                      <TableCell className="font-mono font-semibold">{command.name}</TableCell>
                      <TableCell>
                        {command.aliases.length > 0 ? (
                          <div className="flex gap-1 flex-wrap">
                            {command.aliases.slice(0, 3).map(alias => (
                              <Badge key={alias} variant="outline" className="font-mono text-xs">
                                {alias}
                              </Badge>
                            ))}
                            {command.aliases.length > 3 && (
                              <Badge variant="outline" className="text-xs">
                                +{command.aliases.length - 3}
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-sm">無</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-md">
                        {command.description || (
                          <span className="text-muted-foreground text-sm">無描述</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </main>
  )
}
