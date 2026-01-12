import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Event {
  id: string
  name: string
  type: 'follow' | 'subscription' | 'bits' | 'raid' | 'custom'
  message: string
  enabled: boolean
  triggerCount: number
}

export default function Events() {
  const [searchQuery, setSearchQuery] = useState('')
  const [events, setEvents] = useState<Event[]>([
    {
      id: '1',
      name: '新追隨者',
      type: 'follow',
      message: '感謝 $(user) 的追隨！',
      enabled: true,
      triggerCount: 45,
    },
    {
      id: '2',
      name: '訂閱感謝',
      type: 'subscription',
      message: '感謝 $(user) 訂閱頻道！',
      enabled: true,
      triggerCount: 23,
    },
    {
      id: '3',
      name: 'Bits 感謝',
      type: 'bits',
      message: '感謝 $(user) 贈送 $(amount) bits！',
      enabled: false,
      triggerCount: 12,
    },
    {
      id: '4',
      name: 'Raid 歡迎',
      type: 'raid',
      message: '歡迎來自 $(user) 的 $(count) 位觀眾！',
      enabled: true,
      triggerCount: 8,
    },
  ])

  const filteredEvents = events.filter(event =>
    event.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const toggleEvent = (id: string) => {
    setEvents(
      events.map(event => (event.id === id ? { ...event, enabled: !event.enabled } : event))
    )
  }

  const getEventTypeBadge = (type: string) => {
    const colors: Record<string, string> = {
      follow: 'bg-blue-500/10 text-blue-500',
      subscription: 'bg-purple-500/10 text-purple-500',
      bits: 'bg-yellow-500/10 text-yellow-500',
      raid: 'bg-red-500/10 text-red-500',
      custom: 'bg-green-500/10 text-green-500',
    }
    const labels: Record<string, string> = {
      follow: '追隨',
      subscription: '訂閱',
      bits: 'Bits',
      raid: 'Raid',
      custom: '自訂',
    }
    return <Badge className={colors[type] || ''}>{labels[type] || type}</Badge>
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Events</h1>
          <p className="text-muted-foreground">管理頻道事件和自動回應</p>
        </div>
        <Button>
          <Icon icon="fa-solid fa-plus" wrapperClassName="mr-2 size-4" />
          新增事件
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>事件列表</CardTitle>
          <CardDescription>設定頻道事件觸發時的自動回應</CardDescription>
        </CardHeader>
        <CardContent>
          {/* 搜尋框 */}
          <div className="mb-4 flex items-center gap-2">
            <div className="relative flex-1">
              <Icon
                icon="fa-solid fa-magnifying-glass"
                wrapperClassName="absolute left-2 top-2.5 size-4 text-muted-foreground"
              />
              <Input
                placeholder="搜尋事件..."
                className="pl-8"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          {/* 事件表格 */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>事件名稱</TableHead>
                  <TableHead>類型</TableHead>
                  <TableHead>訊息</TableHead>
                  <TableHead className="text-right">觸發次數</TableHead>
                  <TableHead className="text-center">狀態</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredEvents.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      沒有找到事件
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredEvents.map(event => (
                    <TableRow key={event.id}>
                      <TableCell className="font-medium">{event.name}</TableCell>
                      <TableCell>{getEventTypeBadge(event.type)}</TableCell>
                      <TableCell className="max-w-md truncate">{event.message}</TableCell>
                      <TableCell className="text-right">{event.triggerCount}</TableCell>
                      <TableCell className="text-center">
                        <div className="flex justify-center">
                          <Switch
                            checked={event.enabled}
                            onCheckedChange={() => toggleEvent(event.id)}
                          />
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="ghost" size="sm">
                            編輯
                          </Button>
                          <Button variant="ghost" size="sm">
                            <Icon
                              icon="fa-solid fa-trash"
                              wrapperClassName="size-4 text-destructive"
                            />
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
