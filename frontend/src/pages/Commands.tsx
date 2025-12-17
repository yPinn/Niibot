import { useState } from 'react'
import { Plus, Search, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Command {
  id: string
  name: string
  message: string
  userlevel: string
  count: number
}

export default function Commands() {
  const [searchQuery, setSearchQuery] = useState('')

  // 示範資料
  const commands: Command[] = [
    {
      id: '1',
      name: '!ai',
      message: '詢問 AI 問題',
      userlevel: 'everyone',
      count: 234,
    },
    {
      id: '2',
      name: '!運勢',
      message: '查看今日運勢',
      userlevel: 'everyone',
      count: 156,
    },
    {
      id: '3',
      name: '!so',
      message: 'Shoutout to $(touser)',
      userlevel: 'moderator',
      count: 89,
    },
  ]

  const filteredCommands = commands.filter(cmd =>
    cmd.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getUserlevelBadge = (level: string) => {
    const colors: Record<string, string> = {
      everyone: 'bg-green-500/10 text-green-500',
      subscriber: 'bg-purple-500/10 text-purple-500',
      moderator: 'bg-blue-500/10 text-blue-500',
      owner: 'bg-red-500/10 text-red-500',
    }
    return (
      <span className={`rounded-full px-2 py-1 text-xs font-medium ${colors[level] || ''}`}>
        {level}
      </span>
    )
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Custom Commands</h1>
          <p className="text-muted-foreground">管理您的自訂聊天指令</p>
        </div>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          新增指令
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>指令列表</CardTitle>
          <CardDescription>管理和編輯您的所有自訂指令</CardDescription>
        </CardHeader>
        <CardContent>
          {/* 搜尋框 */}
          <div className="mb-4 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜尋指令..."
                className="pl-8"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          {/* 指令表格 */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>指令名稱</TableHead>
                  <TableHead>訊息</TableHead>
                  <TableHead>權限等級</TableHead>
                  <TableHead className="text-right">使用次數</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCommands.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      沒有找到指令
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredCommands.map(command => (
                    <TableRow key={command.id}>
                      <TableCell className="font-medium">{command.name}</TableCell>
                      <TableCell className="max-w-md truncate">{command.message}</TableCell>
                      <TableCell>{getUserlevelBadge(command.userlevel)}</TableCell>
                      <TableCell className="text-right">{command.count}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="ghost" size="sm">
                            編輯
                          </Button>
                          <Button variant="ghost" size="sm">
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
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
