import { useCallback, useEffect, useRef, useState } from 'react'

import { type ChannelDefaults, getChannelDefaults } from '@/api/channels'
import {
  type CommandConfig,
  type CommandConfigUpdate,
  createCustomCommand,
  deleteCustomCommand,
  getCommandConfigs,
  getRedemptionConfigs,
  type RedemptionConfig,
  toggleCommandConfig,
  updateCommandConfig,
  updateRedemptionConfig,
} from '@/api/commands'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const ROLE_LABELS: Record<string, string> = {
  everyone: '所有人',
  subscriber: '訂閱者',
  vip: 'VIP',
  moderator: '管理員',
  broadcaster: '頻道主',
}

const BUILTIN_DESCRIPTIONS: Record<string, string> = {
  hi: '打招呼',
  help: '列出可用指令',
  uptime: '顯示開播時間',
  ai: 'AI 回答問題',
  運勢: '今日運勢占卜',
  rk: 'TFT 排行榜查詢',
}

const EDITABLE_COMMANDS = ['hi']

const ACTION_TYPE_LABELS: Record<string, string> = {
  vip: 'VIP 授予',
  first: '搶第一公告',
  niibot_auth: 'Niibot 授權',
}

interface EditingState {
  mode: 'edit' | 'create'
  command: CommandConfig | null
}

export default function Commands() {
  useDocumentTitle('指令管理')
  const [commands, setCommands] = useState<CommandConfig[]>([])
  const [redemptions, setRedemptions] = useState<RedemptionConfig[]>([])
  const [defaults, setDefaults] = useState<ChannelDefaults>({
    default_cooldown: 0,
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Sheet state
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [formName, setFormName] = useState('')
  const [formResponse, setFormResponse] = useState('')
  const [formCooldown, setFormCooldown] = useState('')
  const [formRole, setFormRole] = useState('everyone')
  const [formAliases, setFormAliases] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const responseInputRef = useRef<HTMLInputElement>(null)

  // Redemption inline editing
  const [editingRedemption, setEditingRedemption] = useState<string | null>(null)
  const [redemptionName, setRedemptionName] = useState('')

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [cmds, reds, defs] = await Promise.all([
        getCommandConfigs(),
        getRedemptionConfigs(),
        getChannelDefaults(),
      ])
      setCommands(cmds)
      setRedemptions(reds)
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

  // --- Command handlers ---

  const handleToggle = async (cmd: CommandConfig) => {
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

  const hasAdvancedValues = (cmd: CommandConfig) =>
    cmd.cooldown != null || cmd.min_role !== 'everyone' || !!cmd.aliases

  const openEditor = (cmd: CommandConfig) => {
    setEditing({ mode: 'edit', command: cmd })
    setFormName(cmd.command_name)
    setFormResponse(cmd.custom_response || '')
    setFormCooldown(cmd.cooldown != null ? String(cmd.cooldown) : '')
    setFormRole(cmd.min_role)
    setFormAliases(cmd.aliases || '')
    setFormEnabled(cmd.enabled)
    setShowAdvanced(hasAdvancedValues(cmd))
  }

  const openCreate = () => {
    setEditing({ mode: 'create', command: null })
    setFormName('')
    setFormResponse('')
    setFormCooldown('')
    setFormRole('everyone')
    setFormAliases('')
    setFormEnabled(true)
    setShowAdvanced(false)
  }

  /** Convert form string to API value: '' -> null (use default), '0' -> 0, '5' -> 5 */
  const parseCooldown = (value: string): number | null => {
    if (value === '') return null
    return Number(value) || 0
  }

  const handleSave = async () => {
    if (!editing) return
    setSaving(true)
    try {
      if (editing.mode === 'create') {
        if (!formName.trim() || !formResponse.trim()) return
        const created = await createCustomCommand({
          command_name: formName.trim(),
          custom_response: formResponse.trim(),
          cooldown: parseCooldown(formCooldown),
          min_role: formRole,
          aliases: formAliases.trim() || null,
        })
        setCommands(prev => [...prev, created])
      } else if (editing.command) {
        const updates: CommandConfigUpdate = {
          enabled: formEnabled,
          cooldown: parseCooldown(formCooldown),
          min_role: formRole,
          aliases: formAliases.trim() || null,
        }
        if (editing.command.command_type === 'custom') {
          updates.custom_response = formResponse.trim() || null
        }
        if (EDITABLE_COMMANDS.includes(editing.command.command_name)) {
          updates.custom_response = formResponse.trim() || null
        }
        const updated = await updateCommandConfig(editing.command.command_name, updates)
        setCommands(prev => prev.map(c => (c.command_name === updated.command_name ? updated : c)))
      }
      setEditing(null)
    } catch {
      // Keep sheet open
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (cmd: CommandConfig) => {
    if (cmd.command_type !== 'custom') return
    try {
      await deleteCustomCommand(cmd.command_name)
      setCommands(prev => prev.filter(c => c.command_name !== cmd.command_name))
    } catch {
      // Silently fail
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
      const newPos = start + varStr.length
      input.setSelectionRange(newPos, newPos)
    })
  }

  // --- Redemption handlers ---

  const handleRedemptionToggle = async (red: RedemptionConfig) => {
    const newEnabled = !red.enabled
    setRedemptions(prev =>
      prev.map(r => (r.action_type === red.action_type ? { ...r, enabled: newEnabled } : r))
    )
    try {
      await updateRedemptionConfig(red.action_type, {
        reward_name: red.reward_name,
        enabled: newEnabled,
      })
    } catch {
      setRedemptions(prev =>
        prev.map(r => (r.action_type === red.action_type ? { ...r, enabled: red.enabled } : r))
      )
    }
  }

  const startEditRedemption = (red: RedemptionConfig) => {
    setEditingRedemption(red.action_type)
    setRedemptionName(red.reward_name)
  }

  const saveRedemption = async (red: RedemptionConfig) => {
    if (!redemptionName.trim()) return
    try {
      const updated = await updateRedemptionConfig(red.action_type, {
        reward_name: redemptionName.trim(),
        enabled: red.enabled,
      })
      setRedemptions(prev => prev.map(r => (r.action_type === updated.action_type ? updated : r)))
    } catch {
      // Silently fail
    }
    setEditingRedemption(null)
  }

  const formatCooldown = (cooldown: number | null) => {
    const effective = cooldown ?? defaults.default_cooldown
    if (effective <= 0) return '無'
    return cooldown != null ? `${effective}s` : `${effective}s (預設)`
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
      <div>
        <h1 className="text-page-title font-bold">Commands</h1>
        <p className="text-sub text-muted-foreground">管理 Twitch 機器人指令與忠誠點數兌換</p>
      </div>

      {/* Command Configs */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>指令設定</CardTitle>
              <CardDescription>管理內建指令與自訂指令的開關、冷卻、權限</CardDescription>
            </div>
            <Button size="sm" onClick={openCreate}>
              <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
              新增指令
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              載入中...
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-8 text-destructive">{error}</div>
          ) : (
            <Tabs defaultValue="builtin">
              <TabsList>
                <TabsTrigger value="builtin">
                  內建指令
                  <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                    {commands.filter(c => c.command_type === 'builtin').length}
                  </Badge>
                </TabsTrigger>
                <TabsTrigger value="custom">
                  自訂指令
                  <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                    {commands.filter(c => c.command_type === 'custom').length}
                  </Badge>
                </TabsTrigger>
              </TabsList>
              {(['builtin', 'custom'] as const).map(type => {
                const filtered = commands.filter(c => c.command_type === type)
                return (
                  <TabsContent key={type} value={type}>
                    <div className="rounded-md border">
                      <Table className="table-fixed">
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-[35%]">指令</TableHead>
                            <TableHead className="w-[12%]">冷卻</TableHead>
                            <TableHead className="w-[12%]">權限</TableHead>
                            <TableHead className="w-[15%] text-right">使用次數</TableHead>
                            <TableHead className="w-[10%] text-center">狀態</TableHead>
                            <TableHead className="w-[16%] text-right">操作</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filtered.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={6} className="text-center text-muted-foreground">
                                {type === 'custom' ? '尚無自訂指令' : '尚無指令'}
                              </TableCell>
                            </TableRow>
                          ) : (
                            filtered.map(cmd => (
                              <TableRow key={cmd.command_name}>
                                <TableCell>
                                  <div className="flex flex-col">
                                    <div>
                                      <span className="font-mono font-medium">
                                        !{cmd.command_name}
                                      </span>
                                      {cmd.aliases && (
                                        <span className="ml-2 text-label text-muted-foreground">
                                          ({cmd.aliases})
                                        </span>
                                      )}
                                    </div>
                                    <span className="text-label text-muted-foreground truncate max-w-64">
                                      {cmd.command_type === 'builtin'
                                        ? BUILTIN_DESCRIPTIONS[cmd.command_name] || ''
                                        : cmd.custom_response || ''}
                                    </span>
                                  </div>
                                </TableCell>
                                <TableCell className="text-sub text-muted-foreground">
                                  {formatCooldown(cmd.cooldown)}
                                </TableCell>
                                <TableCell className="text-sm">
                                  {ROLE_LABELS[cmd.min_role] || cmd.min_role}
                                </TableCell>
                                <TableCell className="text-right">{cmd.usage_count}</TableCell>
                                <TableCell className="text-center">
                                  <div className="flex justify-center">
                                    <Switch
                                      checked={cmd.enabled}
                                      onCheckedChange={() => handleToggle(cmd)}
                                    />
                                  </div>
                                </TableCell>
                                <TableCell className="text-right">
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8"
                                    onClick={() => openEditor(cmd)}
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
                )
              })}
            </Tabs>
          )}
        </CardContent>
      </Card>

      {/* Redemption Configs */}
      <Card>
        <CardHeader>
          <CardTitle>忠誠點數兌換</CardTitle>
          <CardDescription>設定 Twitch 忠誠點數獎勵名稱與對應動作</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              載入中...
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>動作</TableHead>
                    <TableHead>獎勵名稱</TableHead>
                    <TableHead className="text-center">狀態</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {redemptions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-center text-muted-foreground">
                        尚無兌換設定
                      </TableCell>
                    </TableRow>
                  ) : (
                    redemptions.map(red => (
                      <TableRow key={red.action_type}>
                        <TableCell className="font-medium">
                          {ACTION_TYPE_LABELS[red.action_type] || red.action_type}
                        </TableCell>
                        <TableCell>
                          {editingRedemption === red.action_type ? (
                            <div className="flex items-center gap-2">
                              <Input
                                value={redemptionName}
                                onChange={e => setRedemptionName(e.target.value)}
                                className="h-8 w-48"
                                onKeyDown={e => {
                                  if (e.key === 'Enter') saveRedemption(red)
                                  if (e.key === 'Escape') setEditingRedemption(null)
                                }}
                                autoFocus
                              />
                              <Button size="sm" variant="ghost" onClick={() => saveRedemption(red)}>
                                儲存
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setEditingRedemption(null)}
                              >
                                取消
                              </Button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-sm font-mono hover:bg-accent transition-colors cursor-pointer"
                              onClick={() => startEditRedemption(red)}
                            >
                              {red.reward_name}
                              <Icon
                                icon="fa-solid fa-pen"
                                wrapperClassName="size-3 text-muted-foreground"
                              />
                            </button>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex justify-center">
                            <Switch
                              checked={red.enabled}
                              onCheckedChange={() => handleRedemptionToggle(red)}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Sheet */}
      <Sheet open={!!editing} onOpenChange={open => !open && setEditing(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>
              {editing?.mode === 'create'
                ? '新增自訂指令'
                : `編輯 !${editing?.command?.command_name}`}
            </SheetTitle>
            <SheetDescription>
              {editing?.mode === 'create'
                ? '建立自訂指令，以 ! 開頭的回應會重導向到該指令'
                : '修改指令設定'}
            </SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-6 px-4">
            {/* Command Name (create only) */}
            {editing?.mode === 'create' && (
              <div className="flex flex-col gap-2">
                <Label>指令名稱</Label>
                <div className="flex items-center gap-1">
                  <span className="text-muted-foreground">!</span>
                  <Input
                    value={formName}
                    onChange={e => setFormName(e.target.value)}
                    placeholder="mycommand"
                    className="font-mono"
                  />
                </div>
              </div>
            )}

            {/* Custom Response (custom commands + editable builtins) */}
            {(editing?.mode === 'create' ||
              editing?.command?.command_type === 'custom' ||
              (editing?.command && EDITABLE_COMMANDS.includes(editing.command.command_name))) && (
              <div className="flex flex-col gap-2">
                <Label>回應</Label>
                <Input
                  ref={responseInputRef}
                  value={formResponse}
                  onChange={e => setFormResponse(e.target.value)}
                  placeholder="回應文字 或 !指令名 $(query) 重導向"
                  className="font-mono text-sm"
                />
                <div className="flex flex-col gap-1.5">
                  <span className="text-label text-muted-foreground">可用變數（點擊插入）</span>
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={() => insertVariable('$(user)')}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono hover:bg-accent transition-colors cursor-pointer"
                    >
                      <span className="text-primary">$(user)</span>
                      <span className="text-muted-foreground">— 使用者名稱</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => insertVariable('$(query)')}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono hover:bg-accent transition-colors cursor-pointer"
                    >
                      <span className="text-primary">$(query)</span>
                      <span className="text-muted-foreground">— 使用者輸入</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => insertVariable('$(channel)')}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono hover:bg-accent transition-colors cursor-pointer"
                    >
                      <span className="text-primary">$(channel)</span>
                      <span className="text-muted-foreground">— 頻道名稱</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => insertVariable('$(random 1,100)')}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono hover:bg-accent transition-colors cursor-pointer"
                    >
                      <span className="text-primary">$(random)</span>
                      <span className="text-muted-foreground">— 隨機數字</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => insertVariable('$(pick a,b,c)')}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono hover:bg-accent transition-colors cursor-pointer"
                    >
                      <span className="text-primary">$(pick)</span>
                      <span className="text-muted-foreground">— 隨機選擇</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Enabled */}
            {editing?.mode === 'edit' && (
              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <Label>啟用</Label>
                  <span className="text-xs text-muted-foreground">關閉後指令將不會回應</span>
                </div>
                <Switch checked={formEnabled} onCheckedChange={setFormEnabled} />
              </div>
            )}

            {/* Advanced Settings Toggle */}
            <button
              type="button"
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              onClick={() => setShowAdvanced(prev => !prev)}
            >
              <Icon
                icon={showAdvanced ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                wrapperClassName="size-3"
              />
              {showAdvanced ? '隱藏進階設定' : '顯示進階設定'}
            </button>

            {showAdvanced && (
              <div className="flex flex-col gap-6 border-l-2 border-muted pl-4">
                {/* Aliases */}
                {(editing?.mode === 'create' || editing?.command?.command_type === 'custom') && (
                  <div className="flex flex-col gap-2">
                    <Label>別名</Label>
                    <Input
                      value={formAliases}
                      onChange={e => setFormAliases(e.target.value)}
                      placeholder="hello,hey,hi"
                      className="font-mono text-sm"
                    />
                    <span className="text-xs text-muted-foreground">
                      多個別名用逗號分隔，不含 ! 前綴
                    </span>
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
                    placeholder={`預設: ${defaults.default_cooldown}`}
                    className="w-40"
                  />
                  <span className="text-xs text-muted-foreground">留空則使用頻道預設冷卻設定</span>
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
          </div>

          <SheetFooter className="flex-row gap-2">
            {editing?.mode === 'edit' && editing.command?.command_type === 'custom' && (
              <Button
                variant="destructive"
                onClick={() => {
                  if (editing.command) {
                    handleDelete(editing.command)
                    setEditing(null)
                  }
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
