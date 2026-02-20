import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { type ChannelDefaults, getChannelDefaults } from '@/api/channels'
import {
  type CommandConfig,
  type CommandConfigUpdate,
  createCustomCommand,
  deleteCustomCommand,
  getCommandConfigs,
  toggleCommandConfig,
  updateCommandConfig,
} from '@/api/commands'
import {
  createTrigger,
  deleteTrigger,
  getTriggerConfigs,
  toggleTrigger,
  type TriggerConfig,
  updateTrigger,
} from '@/api/triggers'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Spinner,
  Switch,
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

const ROLE_LABELS: Record<string, string> = {
  everyone: '所有人',
  subscriber: '訂閱者',
  vip: 'VIP',
  moderator: '管理員',
  broadcaster: '頻道主',
}

const EDITABLE_COMMANDS = ['hi']

// English command names sort before Chinese (ASCII charCode < CJK range)
function nameSort(a: string, b: string): number {
  const aAscii = a.charCodeAt(0) < 128
  const bAscii = b.charCodeAt(0) < 128
  if (aAscii !== bAscii) return aAscii ? -1 : 1
  return a.localeCompare(b, 'zh-TW')
}

const ROLE_ORDER: Record<string, number> = {
  everyone: 0,
  subscriber: 1,
  vip: 2,
  moderator: 3,
  broadcaster: 4,
}

type SortKey = 'command_name' | 'cooldown' | 'min_role' | 'usage_count' | 'enabled'
type CustomSortKey = 'name' | 'kind' | 'cooldown' | 'min_role' | 'usage_count'
type SortDir = 'asc' | 'desc'

// Unified editing state: create (type detected by ! prefix), or editing a known item
type EditingState =
  | { mode: 'create' }
  | { mode: 'edit-command'; command: CommandConfig }
  | { mode: 'edit-trigger'; trigger: TriggerConfig }

// Row union for the custom tab
type CustomRow = { kind: 'command'; data: CommandConfig } | { kind: 'trigger'; data: TriggerConfig }

function sanitizeTriggerName(pattern: string): string {
  return (
    pattern
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '')
      .slice(0, 50) || 'trigger'
  )
}

function SortableHead<K extends string>({
  children,
  className,
  sortKey: key,
  currentKey,
  dir,
  onSort,
}: {
  children: React.ReactNode
  className?: string
  sortKey: K
  currentKey: K
  dir: SortDir
  onSort: (key: K) => void
}) {
  const active = key === currentKey
  return (
    <TableHead className={className}>
      <button
        type="button"
        className="inline-flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
        onClick={() => onSort(key)}
      >
        {children}
        <Icon
          icon={
            active
              ? dir === 'asc'
                ? 'fa-solid fa-sort-up'
                : 'fa-solid fa-sort-down'
              : 'fa-solid fa-sort'
          }
          className={active ? 'text-foreground' : 'text-muted-foreground/50'}
          wrapperClassName="size-3"
        />
      </button>
    </TableHead>
  )
}

export default function Commands() {
  useDocumentTitle('Commands')
  const [commands, setCommands] = useState<CommandConfig[]>([])
  const [triggers, setTriggers] = useState<TriggerConfig[]>([])
  const [defaults, setDefaults] = useState<ChannelDefaults>({ default_cooldown: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Sheet state
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [formName, setFormName] = useState('') // !cmd or pattern
  const [formResponse, setFormResponse] = useState('')
  const [formCooldown, setFormCooldown] = useState('')
  const [formRole, setFormRole] = useState('everyone')
  const [formAliases, setFormAliases] = useState('') // command-only
  const [formMatchType, setFormMatchType] = useState<TriggerConfig['match_type']>('startswith')
  const [formCaseSensitive, setFormCaseSensitive] = useState(false)
  const [formPriority, setFormPriority] = useState('0')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('command_name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [customSortKey, setCustomSortKey] = useState<CustomSortKey>('kind')
  const [customSortDir, setCustomSortDir] = useState<SortDir>('asc')
  const responseInputRef = useRef<HTMLInputElement>(null)

  // Derived: is the create form in command mode?
  const formIsCommand = formName.startsWith('!')

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const toggleCustomSort = (key: CustomSortKey) => {
    if (customSortKey === key) {
      setCustomSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setCustomSortKey(key)
      setCustomSortDir('asc')
    }
  }

  const sortBuiltin = useMemo(() => {
    return (list: CommandConfig[]) =>
      [...list].sort((a, b) => {
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
  }, [sortKey, sortDir])

  // Combined custom rows sorted by customSortKey
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
      }
      return customSortDir === 'desc' ? -cmp : cmp
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
    fetchData()
  }, [fetchData])

  // --- Builtin command handlers ---

  const handleToggleCommand = async (cmd: CommandConfig) => {
    const newEnabled = !cmd.enabled
    setCommands(prev =>
      prev.map(c => (c.command_name === cmd.command_name ? { ...c, enabled: newEnabled } : c))
    )
    try {
      await toggleCommandConfig(cmd.command_name, newEnabled)
    } catch {
      setCommands(prev =>
        prev.map(c => (c.command_name === cmd.command_name ? { ...c, enabled: cmd.enabled } : c))
      )
    }
  }

  const handleToggleTrigger = async (trigger: TriggerConfig) => {
    const newEnabled = !trigger.enabled
    setTriggers(prev =>
      prev.map(t => (t.trigger_name === trigger.trigger_name ? { ...t, enabled: newEnabled } : t))
    )
    try {
      await toggleTrigger(trigger.trigger_name, newEnabled)
    } catch {
      setTriggers(prev =>
        prev.map(t =>
          t.trigger_name === trigger.trigger_name ? { ...t, enabled: trigger.enabled } : t
        )
      )
    }
  }

  const handleToggleRow = (row: CustomRow) => {
    if (row.kind === 'command') handleToggleCommand(row.data)
    else handleToggleTrigger(row.data)
  }

  // --- Open sheet helpers ---

  const resetForm = () => {
    setFormResponse('')
    setFormCooldown('5')
    setFormRole('everyone')
    setFormAliases('')
    setFormMatchType('startswith')
    setFormCaseSensitive(false)
    setFormPriority('0')
    setFormEnabled(true)
    setSaveError(null)
    setShowAdvanced(false)
  }

  const openCreate = () => {
    setFormName('!')
    resetForm()
    setEditing({ mode: 'create' })
  }

  const openEditCommand = (cmd: CommandConfig) => {
    setFormName(`!${cmd.command_name}`)
    setFormResponse(cmd.custom_response || '')
    setFormCooldown(cmd.cooldown != null ? String(cmd.cooldown) : '')
    setFormRole(cmd.min_role)
    setFormAliases(cmd.aliases || '')
    setFormEnabled(cmd.enabled)
    setSaveError(null)
    setShowAdvanced(cmd.cooldown != null || cmd.min_role !== 'everyone' || !!cmd.aliases)
    setEditing({ mode: 'edit-command', command: cmd })
  }

  const openEditTrigger = (trigger: TriggerConfig) => {
    setFormName(trigger.pattern)
    setFormResponse(trigger.response)
    setFormCooldown(trigger.cooldown != null ? String(trigger.cooldown) : '')
    setFormRole(trigger.min_role)
    setFormMatchType(trigger.match_type)
    setFormCaseSensitive(trigger.case_sensitive)
    setFormPriority(String(trigger.priority))
    setFormEnabled(trigger.enabled)
    setSaveError(null)
    setShowAdvanced(true)
    setEditing({ mode: 'edit-trigger', trigger })
  }

  const openEditRow = (row: CustomRow) => {
    if (row.kind === 'command') openEditCommand(row.data)
    else openEditTrigger(row.data)
  }

  const parseCooldown = (value: string): number | null => {
    if (value === '') return null
    return Number(value) || 0
  }

  // --- Save handler ---

  const handleSave = async () => {
    if (!editing) return
    setSaving(true)
    setSaveError(null)
    try {
      if (editing.mode === 'create') {
        if (!formName.trim() || !formResponse.trim()) {
          setSaveError('名稱與回應不可為空')
          return
        }
        if (formIsCommand) {
          const cmdName = formName.slice(1).trim()
          if (!cmdName) {
            setSaveError('指令名稱不可為空')
            return
          }
          const created = await createCustomCommand({
            command_name: cmdName,
            custom_response: formResponse.trim(),
            cooldown: parseCooldown(formCooldown),
            min_role: formRole,
            aliases: formAliases.trim() || null,
          })
          setCommands(prev => [...prev, created])
        } else {
          const pattern = formName.trim()
          const triggerName = sanitizeTriggerName(pattern)
          const created = await createTrigger({
            trigger_name: triggerName,
            match_type: formMatchType,
            pattern,
            case_sensitive: formCaseSensitive,
            response: formResponse.trim(),
            min_role: formRole,
            cooldown: parseCooldown(formCooldown),
            priority: Number(formPriority) || 0,
          })
          setTriggers(prev => [...prev, created])
        }
      } else if (editing.mode === 'edit-command') {
        const cmd = editing.command
        const updates: CommandConfigUpdate = {
          enabled: formEnabled,
          cooldown: parseCooldown(formCooldown),
          min_role: formRole,
          aliases: formAliases.trim() || null,
        }
        if (cmd.command_type === 'custom' || EDITABLE_COMMANDS.includes(cmd.command_name)) {
          updates.custom_response = formResponse.trim() || null
        }
        const updated = await updateCommandConfig(cmd.command_name, updates)
        setCommands(prev => prev.map(c => (c.command_name === updated.command_name ? updated : c)))
      } else if (editing.mode === 'edit-trigger') {
        const trigger = editing.trigger
        const updated = await updateTrigger(trigger.trigger_name, {
          match_type: formMatchType,
          pattern: formName.trim(),
          case_sensitive: formCaseSensitive,
          response: formResponse.trim(),
          min_role: formRole,
          cooldown: parseCooldown(formCooldown),
          priority: Number(formPriority) || 0,
          enabled: formEnabled,
        })
        setTriggers(prev => prev.map(t => (t.trigger_name === updated.trigger_name ? updated : t)))
      }
      setEditing(null)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : '儲存失敗')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteCommand = async (cmd: CommandConfig) => {
    if (cmd.command_type !== 'custom') return
    try {
      await deleteCustomCommand(cmd.command_name)
      setCommands(prev => prev.filter(c => c.command_name !== cmd.command_name))
      setEditing(null)
    } catch {
      /* keep sheet open */
    }
  }

  const handleDeleteTrigger = async (trigger: TriggerConfig) => {
    try {
      await deleteTrigger(trigger.trigger_name)
      setTriggers(prev => prev.filter(t => t.trigger_name !== trigger.trigger_name))
      setEditing(null)
    } catch {
      /* keep sheet open */
    }
  }

  const insertVariable = (varStr: string) => {
    const input = responseInputRef.current
    if (!input) {
      setFormResponse(prev => prev + varStr)
      return
    }
    const start = input.selectionStart ?? formResponse.length
    const end = input.selectionEnd ?? formResponse.length
    const newValue = formResponse.slice(0, start) + varStr + formResponse.slice(end)
    setFormResponse(newValue)
    requestAnimationFrame(() => {
      input.focus()
      const pos = start + varStr.length
      input.setSelectionRange(pos, pos)
    })
  }

  const formatCooldown = (cooldown: number | null) => {
    const effective = cooldown ?? defaults.default_cooldown
    if (effective <= 0) return '無'
    return `${effective}s`
  }

  // --- Sheet labels ---
  const sheetTitle = () => {
    if (!editing) return ''
    if (editing.mode === 'create') return formIsCommand ? '新增自訂指令' : '新增自動回應'
    if (editing.mode === 'edit-command') return `編輯 !${editing.command.command_name}`
    return `編輯 ${editing.trigger.trigger_name}`
  }

  const isEditingTrigger = editing?.mode === 'edit-trigger'
  const isCreatingTrigger = editing?.mode === 'create' && !formIsCommand
  const showTriggerFields = isEditingTrigger || isCreatingTrigger

  const isEditingCommand = editing?.mode === 'edit-command'
  const isCreatingCommand = editing?.mode === 'create' && formIsCommand

  const canDelete =
    (editing?.mode === 'edit-command' && editing.command.command_type === 'custom') ||
    editing?.mode === 'edit-trigger'

  return (
    <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
      <div>
        <h1 className="text-page-title font-bold">Commands</h1>
        <p className="text-sub text-muted-foreground">管理 Twitch 機器人指令與自動回應</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>指令設定</CardTitle>
          <CardDescription>
            管理內建指令、自訂指令（!prefix）與自動回應（關鍵字觸發）
          </CardDescription>
          <CardAction>
            <Button size="sm" onClick={openCreate}>
              <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
              新增
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-empty">
              <Spinner className="size-8 text-primary" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-empty text-destructive">
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

              {/* ── Built-in Tab ── */}
              <TabsContent value="builtin">
                <div className="rounded-md border">
                  <Table className="table-fixed">
                    <TableHeader>
                      <TableRow>
                        <SortableHead
                          className="w-[20%]"
                          sortKey="command_name"
                          currentKey={sortKey}
                          dir={sortDir}
                          onSort={toggleSort}
                        >
                          指令
                        </SortableHead>
                        <TableHead>描述</TableHead>
                        <SortableHead
                          className="w-[8%]"
                          sortKey="cooldown"
                          currentKey={sortKey}
                          dir={sortDir}
                          onSort={toggleSort}
                        >
                          冷卻
                        </SortableHead>
                        <SortableHead
                          className="w-[8%]"
                          sortKey="min_role"
                          currentKey={sortKey}
                          dir={sortDir}
                          onSort={toggleSort}
                        >
                          權限
                        </SortableHead>
                        <SortableHead
                          className="w-[10%] text-right"
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
                      {sortBuiltin(commands.filter(c => c.command_type === 'builtin')).map(cmd => (
                        <TableRow key={cmd.command_name}>
                          <TableCell>
                            <div className="flex flex-col">
                              <span className="font-mono font-medium">!{cmd.command_name}</span>
                              {cmd.aliases && (
                                <span className="text-label font-mono text-muted-foreground">
                                  {cmd.aliases
                                    .split(',')
                                    .map(a => `!${a.trim()}`)
                                    .join(' · ')}
                                </span>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-sub text-muted-foreground truncate max-w-0">
                            {cmd.description}
                          </TableCell>
                          <TableCell className="text-sub text-muted-foreground">
                            {formatCooldown(cmd.cooldown)}
                          </TableCell>
                          <TableCell className="text-sub">
                            {ROLE_LABELS[cmd.min_role] || cmd.min_role}
                          </TableCell>
                          <TableCell className="text-right">{cmd.usage_count}</TableCell>
                          <TableCell className="text-center">
                            <div className="flex justify-center">
                              <Switch
                                checked={cmd.enabled}
                                onCheckedChange={() => handleToggleCommand(cmd)}
                              />
                            </div>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-8"
                              onClick={() => openEditCommand(cmd)}
                            >
                              <Icon icon="fa-solid fa-pen" wrapperClassName="size-3.5" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              {/* ── Custom Tab (commands + triggers mixed) ── */}
              <TabsContent value="custom">
                <div className="rounded-md border">
                  <Table className="table-fixed">
                    <TableHeader>
                      <TableRow>
                        <SortableHead
                          className="w-[20%]"
                          sortKey="name"
                          currentKey={customSortKey}
                          dir={customSortDir}
                          onSort={toggleCustomSort}
                        >
                          名稱
                        </SortableHead>
                        <SortableHead
                          className="w-[10%]"
                          sortKey="kind"
                          currentKey={customSortKey}
                          dir={customSortDir}
                          onSort={toggleCustomSort}
                        >
                          類型
                        </SortableHead>
                        <TableHead>回應</TableHead>
                        <SortableHead
                          className="w-[8%]"
                          sortKey="cooldown"
                          currentKey={customSortKey}
                          dir={customSortDir}
                          onSort={toggleCustomSort}
                        >
                          冷卻
                        </SortableHead>
                        <SortableHead
                          className="w-[8%]"
                          sortKey="min_role"
                          currentKey={customSortKey}
                          dir={customSortDir}
                          onSort={toggleCustomSort}
                        >
                          權限
                        </SortableHead>
                        <SortableHead
                          className="w-[10%] text-right"
                          sortKey="usage_count"
                          currentKey={customSortKey}
                          dir={customSortDir}
                          onSort={toggleCustomSort}
                        >
                          使用次數
                        </SortableHead>
                        <TableHead className="w-[7%] text-center">狀態</TableHead>
                        <TableHead className="w-[7%] text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {customRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={8} className="text-center text-muted-foreground">
                            尚無自訂指令或自動回應
                          </TableCell>
                        </TableRow>
                      ) : (
                        customRows.map(row => (
                          <TableRow
                            key={
                              row.kind === 'command'
                                ? `cmd:${row.data.command_name}`
                                : `trg:${row.data.trigger_name}`
                            }
                          >
                            <TableCell>
                              {row.kind === 'command' ? (
                                <div className="flex flex-col">
                                  <span className="font-mono font-medium">
                                    !{row.data.command_name}
                                  </span>
                                  {row.data.aliases && (
                                    <span className="text-label font-mono text-muted-foreground">
                                      {row.data.aliases
                                        .split(',')
                                        .map((a: string) => `!${a.trim()}`)
                                        .join(' · ')}
                                    </span>
                                  )}
                                </div>
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
                            <TableCell className="text-sub text-muted-foreground truncate max-w-0">
                              {row.kind === 'command'
                                ? (row.data.custom_response ?? '')
                                : row.data.response}
                            </TableCell>
                            <TableCell className="text-sub text-muted-foreground">
                              {formatCooldown(row.data.cooldown)}
                            </TableCell>
                            <TableCell className="text-sub">
                              {ROLE_LABELS[row.data.min_role] ?? row.data.min_role}
                            </TableCell>
                            <TableCell className="text-right text-sub text-muted-foreground">
                              {row.data.usage_count}
                            </TableCell>
                            <TableCell className="text-center">
                              <div className="flex justify-center">
                                <Switch
                                  checked={row.data.enabled}
                                  onCheckedChange={() => handleToggleRow(row)}
                                />
                              </div>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8"
                                onClick={() => openEditRow(row)}
                              >
                                <Icon icon="fa-solid fa-pen" wrapperClassName="size-3.5" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>
            </Tabs>
          )}
        </CardContent>
      </Card>

      {/* ── Unified Create/Edit Sheet ── */}
      <Sheet open={!!editing} onOpenChange={open => !open && setEditing(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>{sheetTitle()}</SheetTitle>
            <SheetDescription>
              {editing?.mode === 'create'
                ? '輸入 !name 建立指令，或輸入關鍵字建立自動回應'
                : showTriggerFields
                  ? '修改自動回應設定'
                  : '修改指令設定'}
            </SheetDescription>
          </SheetHeader>

          <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
            {/* Name / Pattern (create + edit trigger) */}
            {(editing?.mode === 'create' || editing?.mode === 'edit-trigger') && (
              <div className="flex flex-col gap-2">
                <Label>{editing.mode === 'create' ? '名稱' : '觸發詞'}</Label>
                <Input
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  placeholder={editing.mode === 'create' ? '!mycommand 或 GG' : 'GG'}
                  className="font-mono"
                  autoFocus
                />
                {editing.mode === 'create' && (
                  <span className="text-label text-muted-foreground">
                    {formIsCommand
                      ? '✓ 將建立為自訂指令（需使用者輸入 !前綴 觸發）'
                      : '✓ 將建立為自動回應（偵測到關鍵字時自動觸發）'}
                  </span>
                )}
              </div>
            )}

            {/* Response — shown for create + custom command edit + trigger edit */}
            {(editing?.mode === 'create' ||
              (isEditingCommand &&
                (editing.command.command_type === 'custom' ||
                  EDITABLE_COMMANDS.includes(editing.command.command_name))) ||
              isEditingTrigger) && (
              <div className="flex flex-col gap-2">
                <Label>回應</Label>
                <Input
                  ref={responseInputRef}
                  value={formResponse}
                  onChange={e => setFormResponse(e.target.value)}
                  placeholder={
                    formIsCommand ? '回應文字 或 !指令名 $(query) 重導向' : '$(user) GG！'
                  }
                  className="font-mono text-sub"
                />
                <div className="flex flex-col gap-1.5">
                  <span className="text-label text-muted-foreground">可用變數（點擊插入）</span>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      { var: '$(user)', desc: '使用者名稱' },
                      { var: '$(query)', desc: '使用者輸入' },
                      { var: '$(channel)', desc: '頻道名稱' },
                      { var: '$(random 1,100)', desc: '隨機數字' },
                      { var: '$(pick a,b,c)', desc: '隨機選擇' },
                    ].map(({ var: v, desc }) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => insertVariable(v)}
                        className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-label font-mono hover:bg-accent transition-colors cursor-pointer"
                      >
                        <span className="text-primary">{v.split(' ')[0]}</span>
                        <span className="text-muted-foreground">— {desc}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Enabled (edit only) */}
            {editing?.mode !== 'create' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <Label>啟用</Label>
                  <span className="text-label text-muted-foreground">關閉後不會回應</span>
                </div>
                <Switch checked={formEnabled} onCheckedChange={setFormEnabled} />
              </div>
            )}

            {/* Advanced toggle */}
            <button
              type="button"
              className="flex items-center gap-2 text-sub text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              onClick={() => setShowAdvanced(prev => !prev)}
            >
              <Icon
                icon={showAdvanced ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                wrapperClassName="size-3"
              />
              {showAdvanced ? '隱藏進階設定' : '顯示進階設定'}
            </button>

            {showAdvanced && (
              <div className="flex flex-col gap-card border-l-2 border-muted pl-page">
                {/* Aliases — command only */}
                {(isCreatingCommand || isEditingCommand) && (
                  <div className="flex flex-col gap-2">
                    <Label>別名</Label>
                    <Input
                      value={formAliases}
                      onChange={e => setFormAliases(e.target.value)}
                      placeholder="hello,hey,hi"
                      className="font-mono text-sub"
                    />
                    <span className="text-label text-muted-foreground">
                      多個別名用逗號分隔，不含 ! 前綴
                    </span>
                  </div>
                )}

                {/* Match type + case sensitive — trigger only */}
                {showTriggerFields && (
                  <>
                    <div className="flex flex-col gap-2">
                      <Label>比對方式</Label>
                      <Select
                        value={formMatchType}
                        onValueChange={v => setFormMatchType(v as TriggerConfig['match_type'])}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="contains">包含關鍵字</SelectItem>
                          <SelectItem value="startswith">以關鍵字開頭</SelectItem>
                          <SelectItem value="exact">完全相符</SelectItem>
                          <SelectItem value="regex">正規表達式</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex flex-col gap-0.5">
                        <Label>區分大小寫</Label>
                        <span className="text-label text-muted-foreground">
                          開啟後 GG 與 gg 視為不同
                        </span>
                      </div>
                      <Switch checked={formCaseSensitive} onCheckedChange={setFormCaseSensitive} />
                    </div>
                  </>
                )}

                {/* Priority — trigger only */}
                {showTriggerFields && (
                  <div className="flex flex-col gap-2">
                    <Label>優先度</Label>
                    <Input
                      type="number"
                      step={1}
                      value={formPriority}
                      onChange={e => setFormPriority(e.target.value)}
                      placeholder="0"
                      className="w-40"
                    />
                    <span className="text-label text-muted-foreground">數字越大優先度越高</span>
                  </div>
                )}

                {/* Cooldown */}
                <div className="flex flex-col gap-2">
                  <Label>冷卻 (秒)</Label>
                  <Input
                    type="number"
                    min={0}
                    step={5}
                    value={formCooldown}
                    onChange={e => setFormCooldown(e.target.value)}
                    placeholder={
                      showTriggerFields ? '建議 30' : `預設: ${defaults.default_cooldown}`
                    }
                    className="w-40"
                  />
                  <span className="text-label text-muted-foreground">
                    {showTriggerFields
                      ? '留空則無冷卻，建議填 30 防洗頻'
                      : '留空則使用頻道預設冷卻設定'}
                  </span>
                </div>

                {/* Min Role */}
                <div className="flex flex-col gap-2">
                  <Label>最低權限</Label>
                  <Select value={formRole} onValueChange={setFormRole}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(ROLE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {saveError && <p className="text-label text-destructive">{saveError}</p>}
          </div>

          <SheetFooter className="shrink-0 flex-row gap-2">
            {canDelete && (
              <Button
                variant="destructive"
                onClick={() => {
                  if (editing?.mode === 'edit-command') handleDeleteCommand(editing.command)
                  else if (editing?.mode === 'edit-trigger') handleDeleteTrigger(editing.trigger)
                }}
              >
                <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
                刪除
              </Button>
            )}
            <div className="flex-1" />
            <SheetClose asChild>
              <Button variant="outline">取消</Button>
            </SheetClose>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? '儲存中...' : '儲存'}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </main>
  )
}
