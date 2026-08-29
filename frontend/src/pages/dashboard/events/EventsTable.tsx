import type { EventConfig, EventDefinition } from '@/api/events'
import { EmptyState, Icon, SlideUp } from '@/components/primitives'
import { SortableHead } from '@/components/SortableHead'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
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
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import type { SortState } from '@/hooks/useSortState'

import { accentClass } from './constants'
import type { EventSortKey } from './types'

interface EventsTableProps {
  events: EventConfig[]
  catalog: Map<string, EventDefinition>
  loading: boolean
  error: string | null
  sort: SortState<EventSortKey>
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
            <TableSkeletonRows count={4} />
          ) : error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    <SortableHead className="w-[16%]" sortKey="event_type" sort={sort}>
                      事件名稱
                    </SortableHead>
                    <SortableHead
                      className="hidden md:table-cell w-[10%]"
                      sortKey="type_label"
                      sort={sort}
                    >
                      類型
                    </SortableHead>
                    <TableHead className="hidden md:table-cell">訊息模板</TableHead>
                    <SortableHead
                      className="hidden lg:table-cell w-[9%] text-right"
                      sortKey="trigger_count"
                      sort={sort}
                    >
                      觸發次數
                    </SortableHead>
                    <SortableHead className="w-[9%] text-center" sortKey="enabled" sort={sort}>
                      狀態
                    </SortableHead>
                    <TableHead className="w-[8%] text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6}>
                        <EmptyState icon="fa-solid fa-bell" title="尚無事件設定" />
                      </TableCell>
                    </TableRow>
                  )}
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
                        <TableCell className="hidden lg:table-cell text-right">
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
