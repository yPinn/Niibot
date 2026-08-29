import type { EventConfig, EventDefinition } from '@/api/events'
import { Icon, SlideUp } from '@/components/primitives'
import { SortableHead } from '@/components/SortableHead'
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import type { useSortState } from '@/hooks/useSortState'

import { accentClass } from './constants'
import type { EventSortKey } from './types'

interface EventsTableProps {
  events: EventConfig[]
  catalog: Map<string, EventDefinition>
  loading: boolean
  error: string | null
  sort: ReturnType<typeof useSortState<EventSortKey>>
  isAffiliate: boolean
  onToggle: (event: EventConfig) => void
  onEdit: (event: EventConfig) => void
}

export function EventsTable({
  events,
  catalog,
  loading,
  error,
  sort,
  isAffiliate,
  onToggle,
  onEdit,
}: EventsTableProps) {
  return (
    <SlideUp inView>
      <Card>
        <CardHeader>
          <CardTitle>事件列表</CardTitle>
          <CardDescription>設定頻道事件觸發時的自動回應訊息</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    <SortableHead
                      className="w-[20%]"
                      sortKey="event_type"
                      currentKey={sort.sortKey}
                      dir={sort.sortDir}
                      onSort={sort.toggleSort}
                    >
                      事件名稱
                    </SortableHead>
                    <SortableHead
                      className="hidden md:table-cell w-[12%]"
                      sortKey="type_label"
                      currentKey={sort.sortKey}
                      dir={sort.sortDir}
                      onSort={sort.toggleSort}
                    >
                      類型
                    </SortableHead>
                    <TableHead className="hidden md:table-cell">訊息模板</TableHead>
                    <SortableHead
                      className="hidden md:table-cell w-[12%] text-right"
                      sortKey="trigger_count"
                      currentKey={sort.sortKey}
                      dir={sort.sortDir}
                      onSort={sort.toggleSort}
                    >
                      觸發次數
                    </SortableHead>
                    <SortableHead
                      className="w-[10%] text-center"
                      sortKey="enabled"
                      currentKey={sort.sortKey}
                      dir={sort.sortDir}
                      onSort={sort.toggleSort}
                    >
                      狀態
                    </SortableHead>
                    <TableHead className="w-[8%] text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.map(event => {
                    const defn = catalog.get(event.event_type)
                    const name = defn?.display_name ?? event.event_type
                    const locked = !isAffiliate && (defn?.requires_affiliate ?? false)
                    return (
                      <TableRow key={event.event_type} className={locked ? 'opacity-50' : ''}>
                        <TableCell className="font-medium">
                          <span className="flex items-center gap-1.5">
                            {name}
                            {locked && <Icon icon="fa-solid fa-lock" wrapperClassName="size-3.5" />}
                          </span>
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          {defn && (
                            <Badge className={accentClass(defn.accent)}>
                              {defn.category_label}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="hidden md:table-cell max-w-0 truncate font-mono text-label">
                          {locked ? (
                            <span className="text-muted-foreground">需要實況盟友資格</span>
                          ) : (
                            event.message_template
                          )}
                        </TableCell>
                        <TableCell className="hidden md:table-cell text-right">
                          {event.trigger_count ?? '—'}
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            aria-label={`啟用 ${name}`}
                            checked={event.enabled}
                            onCheckedChange={() => onToggle(event)}
                            disabled={locked}
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onEdit(event)}
                            disabled={locked}
                          >
                            編輯
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </SlideUp>
  )
}
