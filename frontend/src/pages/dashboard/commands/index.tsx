import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { type ChannelDefaults, getChannelDefaults } from '@/api/channels'
import { type CommandConfig, getCommandConfigs, toggleCommandConfig } from '@/api/commands'
import { getTriggerConfigs, toggleTrigger, type TriggerConfig } from '@/api/triggers'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, SlideUp } from '@/components/primitives'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'
import { applyDir, nameSort, ROLE_ORDER } from '@/lib/sort'

import { BuiltinTab } from './BuiltinTab'
import { CommandSheet } from './CommandSheet'
import { CustomTab } from './CustomTab'
import { ImportSheet } from './ImportSheet'
import type { CustomRow, CustomSortKey, EditingState, SortKey } from './types'

/** Error codes the Nightbot OAuth callback can append to the return URL. */
const IMPORT_ERRORS: Record<string, string> = {
  invalid_state: '授權連結無效，請重新開始匯入',
  no_code: '沒有收到 Nightbot 的授權碼，請重新開始匯入',
  token_exchange_failed: 'Nightbot 授權失敗，請重新開始匯入',
  channel_not_found: '找不到你的頻道',
  fetch_failed: '讀取 Nightbot 指令失敗，請稍後再試',
  access_denied: '你取消了 Nightbot 授權',
}

export default function Commands() {
  useDocumentTitle('Commands')

  const [commands, setCommands] = useState<CommandConfig[]>([])
  const [triggers, setTriggers] = useState<TriggerConfig[]>([])
  const [defaults, setDefaults] = useState<ChannelDefaults>({ default_cooldown: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  // The Nightbot OAuth callback redirects back here with a preview waiting.
  const [importState, setImportState] = useState<{ open: boolean; importId: string | null }>(() => {
    const importId = searchParams.get('import_id')
    return { open: Boolean(importId), importId }
  })

  const builtinSort = useSortState<SortKey>('catalog_order')
  const customSort = useSortState<CustomSortKey>('kind')

  const { toggle: toggleCommand } = useOptimisticToggle<CommandConfig>({
    setState: setCommands,
    getId: c => c.command_name,
    toggleFn: (c, enabled) => toggleCommandConfig(c.command_name, enabled).then(() => {}),
    messages: { on: '指令已啟用', off: '指令已停用', error: '切換指令狀態失敗' },
  })

  const { toggle: toggleTriggerItem } = useOptimisticToggle<TriggerConfig>({
    setState: setTriggers,
    getId: t => t.trigger_name,
    toggleFn: (t, enabled) => toggleTrigger(t.trigger_name, enabled).then(() => {}),
    messages: { on: '觸發器已啟用', off: '觸發器已停用', error: '切換觸發器狀態失敗' },
  })

  const handleToggleRow = (row: CustomRow) => {
    if (row.kind === 'command') toggleCommand(row.data)
    else toggleTriggerItem(row.data)
  }

  const { sortKey: customSortKey, sortDir: customSortDir } = customSort
  const customRows = useMemo((): CustomRow[] => {
    const all: CustomRow[] = [
      ...commands
        .filter(c => c.command_type === 'custom')
        .map((c): CustomRow => ({ kind: 'command', data: c })),
      ...triggers.map((t): CustomRow => ({ kind: 'trigger', data: t })),
    ]
    all.sort((a, b) => {
      let cmp = 0
      const nameA = a.kind === 'command' ? a.data.command_name : a.data.pattern
      const nameB = b.kind === 'command' ? b.data.command_name : b.data.pattern
      switch (customSortKey) {
        case 'name':
          cmp = nameSort(nameA, nameB)
          break
        case 'kind': {
          const kindCmp = (a.kind === 'command' ? 0 : 1) - (b.kind === 'command' ? 0 : 1)
          cmp = kindCmp !== 0 ? kindCmp : nameSort(nameA, nameB)
          break
        }
        case 'cooldown':
          cmp = (a.data.cooldown ?? -1) - (b.data.cooldown ?? -1)
          break
        case 'min_role':
          cmp = (ROLE_ORDER[a.data.min_role] ?? 0) - (ROLE_ORDER[b.data.min_role] ?? 0)
          break
        case 'usage_count':
          cmp = a.data.usage_count - b.data.usage_count
          break
        case 'enabled':
          cmp = Number(a.data.enabled) - Number(b.data.enabled)
          break
      }
      return applyDir(cmp, customSortDir)
    })
    return all
  }, [commands, triggers, customSortKey, customSortDir])

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [cmds, trgs, defs] = await Promise.all([
        getCommandConfigs(),
        getTriggerConfigs(),
        getChannelDefaults(),
      ])
      setCommands(cmds)
      setTriggers(trgs)
      setDefaults(defs)
    } catch {
      setError('無法載入設定')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchData()
  }, [fetchData])

  // Consume the OAuth return params once, so a refresh does not replay them.
  useEffect(() => {
    const importError = searchParams.get('import_error')
    if (importError) toast.error(IMPORT_ERRORS[importError] ?? '匯入失敗，請再試一次')
    if (importError || searchParams.get('import_id')) setSearchParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreate = () => setEditing({ mode: 'create' })

  const openEditCommand = (cmd: CommandConfig) => setEditing({ mode: 'edit-command', command: cmd })

  const openEditTrigger = (trigger: TriggerConfig) => setEditing({ mode: 'edit-trigger', trigger })

  const openEditRow = (row: CustomRow) => {
    if (row.kind === 'command') openEditCommand(row.data)
    else openEditTrigger(row.data)
  }

  const handleSaved = ({
    commands: updatedCmds,
    triggers: updatedTrgs,
  }: {
    commands?: CommandConfig[]
    triggers?: TriggerConfig[]
  }) => {
    if (updatedCmds) {
      setCommands(prev => {
        const map = new Map(prev.map(c => [c.command_name, c]))
        updatedCmds.forEach(c => map.set(c.command_name, c))
        // New items (create) won't be in map yet — add them
        const newOnes = updatedCmds.filter(c => !prev.some(p => p.command_name === c.command_name))
        return [...prev.map(c => map.get(c.command_name) ?? c), ...newOnes]
      })
    }
    if (updatedTrgs) {
      setTriggers(prev => {
        const map = new Map(prev.map(t => [t.trigger_name, t]))
        updatedTrgs.forEach(t => map.set(t.trigger_name, t))
        const newOnes = updatedTrgs.filter(t => !prev.some(p => p.trigger_name === t.trigger_name))
        return [...prev.map(t => map.get(t.trigger_name) ?? t), ...newOnes]
      })
    }
  }

  const handleDeleted = (kind: 'command' | 'trigger', name: string) => {
    if (kind === 'command') {
      setCommands(prev => prev.filter(c => c.command_name !== name))
    } else {
      setTriggers(prev => prev.filter(t => t.trigger_name !== name))
    }
  }

  return (
    <PageMain>
      <PageHeader title="Commands" description="管理 Twitch 機器人指令與自動回應" />

      <SlideUp inView>
        <Card>
          <CardHeader>
            <CardTitle>指令設定</CardTitle>
            <CardDescription>
              管理內建指令、自訂指令（!prefix）與自動回應（關鍵字觸發）
            </CardDescription>
            <CardAction className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setImportState({ open: true, importId: null })}
              >
                <Icon icon="fa-solid fa-file-import" wrapperClassName="mr-1.5 size-3" />
                匯入
              </Button>
              <Button size="sm" onClick={openCreate}>
                <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
                新增
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                <Skeleton className="h-9 w-48" />
                <TableSkeletonRows count={6} />
              </div>
            ) : error ? (
              <div className="flex items-center justify-center py-empty text-sub text-destructive">
                {error}
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
                      {commands.filter(c => c.command_type === 'custom').length + triggers.length}
                    </Badge>
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="builtin">
                  <BuiltinTab
                    commands={commands.filter(c => c.command_type === 'builtin')}
                    sortState={builtinSort}
                    defaults={defaults}
                    onToggle={toggleCommand}
                    onEdit={openEditCommand}
                  />
                </TabsContent>

                <TabsContent value="custom">
                  <CustomTab
                    customRows={customRows}
                    sortState={customSort}
                    defaults={defaults}
                    onToggle={handleToggleRow}
                    onEdit={openEditRow}
                  />
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      <CommandSheet
        open={!!editing}
        editing={editing}
        defaults={defaults}
        onSaved={handleSaved}
        onDeleted={handleDeleted}
        onClose={() => setEditing(null)}
      />

      <ImportSheet
        open={importState.open}
        initialImportId={importState.importId}
        onImported={fetchData}
        onClose={() => setImportState({ open: false, importId: null })}
      />
    </PageMain>
  )
}
