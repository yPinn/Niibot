import { useMemo } from 'react'

import type { ChannelDefaults } from '@/api/channels'
import type { CommandConfig } from '@/api/commands'
import { Icon } from '@/components/primitives'
import { SortableHead } from '@/components/SortableHead'
import {
  Button,
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
import { nameSort, ROLE_ORDER } from '@/lib/sort'

import { formatCooldown, ROLE_LABELS } from './constants'
import type { SortKey } from './types'

export interface BuiltinTabProps {
  commands: CommandConfig[]
  sortState: SortState<SortKey>
  defaults: ChannelDefaults
  onToggle: (cmd: CommandConfig) => void
  onEdit: (cmd: CommandConfig) => void
}

export function BuiltinTab({ commands, sortState, defaults, onToggle, onEdit }: BuiltinTabProps) {
  const { sortKey, sortDir } = sortState

  const sorted = useMemo(() => {
    return [...commands].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'command_name':
          cmp = nameSort(a.command_name, b.command_name)
          break
        case 'cooldown':
          cmp = (a.cooldown ?? -1) - (b.cooldown ?? -1)
          break
        case 'min_role':
          cmp = (ROLE_ORDER[a.min_role] ?? 0) - (ROLE_ORDER[b.min_role] ?? 0)
          break
        case 'usage_count':
          cmp = a.usage_count - b.usage_count
          break
        case 'enabled':
          cmp = Number(a.enabled) - Number(b.enabled)
          break
      }
      return sortDir === 'desc' ? -cmp : cmp
    })
  }, [commands, sortKey, sortDir])

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            <SortableHead className="w-[20%]" sortKey="command_name" sort={sortState}>
              指令
            </SortableHead>
            <TableHead className="hidden md:table-cell">描述</TableHead>
            <SortableHead
              className="hidden md:table-cell w-[8%]"
              sortKey="cooldown"
              sort={sortState}
            >
              冷卻
            </SortableHead>
            <SortableHead
              className="hidden md:table-cell w-[8%]"
              sortKey="min_role"
              sort={sortState}
            >
              權限
            </SortableHead>
            <SortableHead
              className="hidden md:table-cell w-[10%] text-right"
              sortKey="usage_count"
              sort={sortState}
            >
              使用次數
            </SortableHead>
            <SortableHead className="w-[8%] text-center" sortKey="enabled" sort={sortState}>
              狀態
            </SortableHead>
            <TableHead className="w-[7%] text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map(cmd => (
            <TableRow key={cmd.command_name}>
              <TableCell>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono font-medium">!{cmd.command_name}</span>
                  {cmd.aliases && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="cursor-default text-muted-foreground">
                          <Icon icon="fa-solid fa-tags" wrapperClassName="size-3" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        <span className="font-mono">
                          {cmd.aliases
                            .split(',')
                            .map(a => `!${a.trim()}`)
                            .join(' · ')}
                        </span>
                      </TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </TableCell>
              <TableCell className="hidden md:table-cell max-w-0 truncate text-sub text-muted-foreground">
                {cmd.description}
              </TableCell>
              <TableCell className="hidden md:table-cell text-sub text-muted-foreground">
                {formatCooldown(cmd.cooldown, defaults)}
              </TableCell>
              <TableCell className="hidden md:table-cell text-sub">
                {ROLE_LABELS[cmd.min_role] || cmd.min_role}
              </TableCell>
              <TableCell className="hidden md:table-cell text-right">{cmd.usage_count}</TableCell>
              <TableCell className="text-center">
                <Switch checked={cmd.enabled} onCheckedChange={() => onToggle(cmd)} />
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8"
                  aria-label={`編輯 !${cmd.command_name}`}
                  onClick={() => onEdit(cmd)}
                >
                  <Icon icon="fa-solid fa-pen" wrapperClassName="size-3.5" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
