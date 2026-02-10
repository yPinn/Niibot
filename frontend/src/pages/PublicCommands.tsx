import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getPublicCommands, type PublicCommand } from '@/api/commands'
import { useTheme } from '@/components/theme-provider'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export default function PublicCommands() {
  const { username } = useParams<{ username: string }>()
  const { resolvedTheme, setTheme } = useTheme()
  const [commands, setCommands] = useState<PublicCommand[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!username) return
    getPublicCommands(username)
      .then(setCommands)
      .catch(() => setError('找不到該頻道或無法載入指令'))
      .finally(() => setLoading(false))
  }, [username])

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12">
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
        <Card className="rounded-2xl border shadow-xl">
          <CardHeader>
            {/* Avatar + Title */}
            <div className="flex flex-col items-center">
              <Avatar className="mb-4 h-24 w-24 border-4 border-primary shadow-lg">
                <AvatarImage
                  src={`https://logo.clearbit.com/twitch.tv/${username}`}
                  alt={`${username} avatar`}
                />
                <AvatarFallback>
                  <img src="/images/Avatar.png" alt="fallback" className="h-full w-full" />
                </AvatarFallback>
              </Avatar>
              <CardTitle className="text-center text-page-title">{username} 的指令列表</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                載入中...
              </div>
            ) : error ? (
              <div className="flex items-center justify-center py-8 text-destructive">{error}</div>
            ) : commands.length === 0 ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                尚無指令
              </div>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[30%]">指令</TableHead>
                      <TableHead>說明</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {commands.map(cmd => (
                      <TableRow key={cmd.name}>
                        <TableCell className="font-mono font-medium">{cmd.name}</TableCell>
                        <TableCell className="text-muted-foreground">{cmd.description}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
