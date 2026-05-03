import type { ChannelDefaults } from '@/api/channels'
import { SortableHead } from '@/components/SortableHead'
import {
  Badge,
  Button,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Icon,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import type { SortState } from '@/hooks/useSortState'

import { formatCooldown, ROLE_LABELS } from './constants'
import type { CustomRow, CustomSortKey } from './types'

export interface CustomTabProps {
  customRows: CustomRow[]
  sortState: SortState<CustomSortKey>
  defaults: ChannelDefaults
  onToggle: (row: CustomRow) => void
  onEdit: (row: CustomRow) => void
}

export function CustomTab({ customRows, sortState, defaults, onToggle, onEdit }: CustomTabProps) {
  const { sortKey, sortDir, toggleSort } = sortState

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            <SortableHead
              className="w-[20%]"
              sortKey="name"
              currentKey={sortKey}
              dir={sortDir}
              onSort={toggleSort}
            >
              名稱
            </SortableHead>
            <SortableHead
              className="w-[10%]"
              sortKey="kind"
              currentKey={sortKey}
              dir={sortDir}
              onSort={toggleSort}
            >
              類型
            </SortableHead>
            <TableHead className="hidden md:table-cell">回應</TableHead>
            <SortableHead
              className="hidden md:table-cell w-[8%]"
              sortKey="cooldown"
              currentKey={sortKey}
              dir={sortDir}
              onSort={toggleSort}
            >
              冷卻
            </SortableHead>
            <SortableHead
              className="hidden md:table-cell w-[8%]"
              sortKey="min_role"
              currentKey={sortKey}
              dir={sortDir}
              onSort={toggleSort}
            >
              權限
            </SortableHead>
            <SortableHead
              className="hidden md:table-cell w-[10%] text-right"
              sortKey="usage_count"
              currentKey={sortKey}
              dir={sortDir}
              onSort={toggleSort}
            >
              使用次數
            </SortableHead>
            <SortableHead
              className="w-[8%] text-center"
              sortKey="enabled"
              currentKey={sortKey}
              dir={sortDir}
              onSort={toggleSort}
            >
              狀態
            </SortableHead>
            <TableHead className="w-[7%] text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {customRows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8}>
                <Empty className="border-none">
                  <EmptyHeader>
                    <EmptyMedia>
                      <Icon
                        icon="fa-solid fa-terminal"
                        wrapperClassName="size-20 opacity-25"
                        className="text-[5rem]"
                      />
                    </EmptyMedia>
                    <EmptyTitle>尚無自訂指令或自動回應</EmptyTitle>
                    <EmptyDescription>點擊「新增」開始建立指令</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </TableCell>
            </TableRow>
          ) : (
            customRows.map(row => {
              const key =
                row.kind === 'command'
                  ? `cmd:${row.data.command_name}`
                  : `trg:${row.data.trigger_name}`
              const label = row.kind === 'command' ? `編輯 !${row.data.command_name}` : `編輯觸發器`

              return (
                <TableRow key={key}>
                  <TableCell>
                    {row.kind === 'command' ? (
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-medium">!{row.data.command_name}</span>
                        {row.data.aliases && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="cursor-default text-muted-foreground">
                                <Icon icon="fa-solid fa-tags" wrapperClassName="size-3" />
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              <span className="font-mono">
                                {row.data.aliases
                                  .split(',')
                                  .map((a: string) => `!${a.trim()}`)
                                  .join(' · ')}
                              </span>
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    ) : row.data.match_type === 'regex' ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="cursor-default font-mono text-sub">
                            {row.data.pattern.length > 24
                              ? `${row.data.pattern.slice(0, 22)}…`
                              : row.data.pattern}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-80">
                          <span className="break-all font-mono text-xs">{row.data.pattern}</span>
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <span className="font-mono text-sub">{row.data.pattern}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {row.kind === 'command' ? (
                      <Badge variant="default">指令</Badge>
                    ) : (
                      <Badge variant="secondary">觸發</Badge>
                    )}
                  </TableCell>
                  <TableCell className="hidden md:table-cell max-w-0 truncate text-sub text-muted-foreground">
                    {row.kind === 'command' ? (row.data.custom_response ?? '') : row.data.response}
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-sub text-muted-foreground">
                    {formatCooldown(row.data.cooldown, defaults)}
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-sub">
                    {ROLE_LABELS[row.data.min_role] ?? row.data.min_role}
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-right">
                    {row.data.usage_count}
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex justify-center">
                      <Switch checked={row.data.enabled} onCheckedChange={() => onToggle(row)} />
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      aria-label={label}
                      onClick={() => onEdit(row)}
                    >
                      <Icon icon="fa-solid fa-pen" wrapperClassName="size-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>
    </div>
  )
}
