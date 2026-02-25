import { useEffect, useReducer } from 'react'
import { toast } from 'sonner'

import { type ChannelDefaults } from '@/api/channels'
import {
  type CommandConfig,
  type CommandConfigUpdate,
  createCustomCommand,
  deleteCustomCommand,
  updateCommandConfig,
} from '@/api/commands'
import { createTrigger, deleteTrigger, type TriggerConfig, updateTrigger } from '@/api/triggers'
import {
  Button,
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
  Switch,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useInputInsert } from '@/hooks/useInputInsert'

import { EDITABLE_COMMANDS, ROLE_LABELS } from './constants'
import type { EditingState } from './types'

// ---------------------------------------------------------------------------
// Form state via useReducer
// ---------------------------------------------------------------------------

interface FormState {
  name: string
  response: string
  cooldown: string
  role: string
  aliases: string
  matchType: TriggerConfig['match_type']
  caseSensitive: boolean
  priority: string
  enabled: boolean
  showAdvanced: boolean
  saving: boolean
  saveError: string | null
}

type FormAction =
  | {
      type: 'SET'
      field: keyof Omit<FormState, 'saving' | 'saveError'>
      value: FormState[keyof FormState]
    }
  | { type: 'SAVING' }
  | { type: 'SAVE_ERROR'; msg: string }
  | { type: 'SAVE_DONE' }
  | { type: 'RESET'; partial: Partial<FormState> }

function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case 'SET':
      return { ...state, [action.field]: action.value }
    case 'SAVING':
      return { ...state, saving: true, saveError: null }
    case 'SAVE_ERROR':
      return { ...state, saving: false, saveError: action.msg }
    case 'SAVE_DONE':
      return { ...state, saving: false }
    case 'RESET':
      return { ...initialForm, ...action.partial }
    default:
      return state
  }
}

const initialForm: FormState = {
  name: '',
  response: '',
  cooldown: '5',
  role: 'everyone',
  aliases: '',
  matchType: 'startswith',
  caseSensitive: false,
  priority: '0',
  enabled: true,
  showAdvanced: false,
  saving: false,
  saveError: null,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseCooldown(value: string): number | null {
  if (value === '') return null
  return Number(value) || 0
}

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

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CommandSheetProps {
  open: boolean
  editing: EditingState | null
  defaults: ChannelDefaults
  onSaved: (result: { commands?: CommandConfig[]; triggers?: TriggerConfig[] }) => void
  onDeleted: (kind: 'command' | 'trigger', name: string) => void
  onClose: () => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CommandSheet({
  open,
  editing,
  defaults,
  onSaved,
  onDeleted,
  onClose,
}: CommandSheetProps) {
  const [form, dispatch] = useReducer(formReducer, initialForm)

  // Sync form when editing changes (sheet opens / switches item)
  useEffect(() => {
    if (!editing) return
    if (editing.mode === 'create') {
      dispatch({ type: 'RESET', partial: { name: '!', cooldown: '5' } })
    } else if (editing.mode === 'edit-command') {
      const cmd = editing.command
      dispatch({
        type: 'RESET',
        partial: {
          name: `!${cmd.command_name}`,
          response: cmd.custom_response || '',
          cooldown: cmd.cooldown != null ? String(cmd.cooldown) : '',
          role: cmd.min_role,
          aliases: cmd.aliases || '',
          enabled: cmd.enabled,
          showAdvanced: cmd.cooldown != null || cmd.min_role !== 'everyone' || !!cmd.aliases,
        },
      })
    } else if (editing.mode === 'edit-trigger') {
      const t = editing.trigger
      dispatch({
        type: 'RESET',
        partial: {
          name: t.pattern,
          response: t.response,
          cooldown: t.cooldown != null ? String(t.cooldown) : '',
          role: t.min_role,
          matchType: t.match_type,
          caseSensitive: t.case_sensitive,
          priority: String(t.priority),
          enabled: t.enabled,
          showAdvanced: true,
        },
      })
    }
  }, [editing])

  const { inputRef, insertText } = useInputInsert(form.response, newVal =>
    dispatch({ type: 'SET', field: 'response', value: newVal })
  )

  const formIsCommand = form.name.startsWith('!')
  const isEditingTrigger = editing?.mode === 'edit-trigger'
  const isCreatingTrigger = editing?.mode === 'create' && !formIsCommand
  const showTriggerFields = isEditingTrigger || isCreatingTrigger
  const isEditingCommand = editing?.mode === 'edit-command'
  const isCreatingCommand = editing?.mode === 'create' && formIsCommand
  const canDelete =
    (editing?.mode === 'edit-command' && editing.command.command_type === 'custom') ||
    editing?.mode === 'edit-trigger'

  const sheetTitle = () => {
    if (!editing) return ''
    if (editing.mode === 'create') return formIsCommand ? '新增自訂指令' : '新增自動回應'
    if (editing.mode === 'edit-command') return `編輯 !${editing.command.command_name}`
    return `編輯 ${editing.trigger.trigger_name}`
  }

  const handleSave = async () => {
    if (!editing) return
    dispatch({ type: 'SAVING' })

    try {
      if (editing.mode === 'create') {
        if (!form.name.trim() || !form.response.trim()) {
          dispatch({ type: 'SAVE_ERROR', msg: '名稱與回應不可為空' })
          return
        }
        if (formIsCommand) {
          const cmdName = form.name.slice(1).trim()
          if (!cmdName) {
            dispatch({ type: 'SAVE_ERROR', msg: '指令名稱不可為空' })
            return
          }
          const created = await createCustomCommand({
            command_name: cmdName,
            custom_response: form.response.trim(),
            cooldown: parseCooldown(form.cooldown),
            min_role: form.role,
            aliases: form.aliases.trim() || null,
          })
          onSaved({ commands: [created] })
        } else {
          const pattern = form.name.trim()
          const created = await createTrigger({
            trigger_name: sanitizeTriggerName(pattern),
            match_type: form.matchType,
            pattern,
            case_sensitive: form.caseSensitive,
            response: form.response.trim(),
            min_role: form.role,
            cooldown: parseCooldown(form.cooldown),
            priority: Number(form.priority) || 0,
          })
          onSaved({ triggers: [created] })
        }
      } else if (editing.mode === 'edit-command') {
        const cmd = editing.command
        const updates: CommandConfigUpdate = {
          enabled: form.enabled,
          cooldown: parseCooldown(form.cooldown),
          min_role: form.role,
          aliases: form.aliases.trim() || null,
        }
        if (cmd.command_type === 'custom' || EDITABLE_COMMANDS.includes(cmd.command_name)) {
          updates.custom_response = form.response.trim() || null
        }
        const updated = await updateCommandConfig(cmd.command_name, updates)
        onSaved({ commands: [updated] })
      } else if (editing.mode === 'edit-trigger') {
        const updated = await updateTrigger(editing.trigger.trigger_name, {
          match_type: form.matchType,
          pattern: form.name.trim(),
          case_sensitive: form.caseSensitive,
          response: form.response.trim(),
          min_role: form.role,
          cooldown: parseCooldown(form.cooldown),
          priority: Number(form.priority) || 0,
          enabled: form.enabled,
        })
        onSaved({ triggers: [updated] })
      }
      toast.success(editing.mode === 'create' ? '建立成功' : '已儲存變更')
      onClose()
    } catch (e) {
      const msg = e instanceof Error ? e.message : '儲存失敗'
      dispatch({ type: 'SAVE_ERROR', msg })
      toast.error('儲存失敗', { description: msg })
    } finally {
      dispatch({ type: 'SAVE_DONE' })
    }
  }

  const handleDelete = async () => {
    if (!editing) return
    try {
      if (editing.mode === 'edit-command') {
        await deleteCustomCommand(editing.command.command_name)
        onDeleted('command', editing.command.command_name)
        toast.success('指令已刪除')
      } else if (editing.mode === 'edit-trigger') {
        await deleteTrigger(editing.trigger.trigger_name)
        onDeleted('trigger', editing.trigger.trigger_name)
        toast.success('觸發器已刪除')
      }
      onClose()
    } catch {
      toast.error('刪除失敗')
    }
  }

  // Variable chips per context
  const commandVars = [
    { var: '$(user)', desc: '使用者名稱' },
    { var: '$(query)', desc: '使用者輸入' },
    { var: '$(channel)', desc: '頻道名稱' },
    { var: '$(random 1,100)', desc: '隨機數字' },
    { var: '$(pick a,b,c)', desc: '隨機選擇' },
  ]

  const showResponseField =
    editing?.mode === 'create' ||
    (isEditingCommand &&
      (editing.command.command_type === 'custom' ||
        EDITABLE_COMMANDS.includes(editing.command.command_name))) ||
    isEditingTrigger

  return (
    <Sheet open={open} onOpenChange={o => !o && onClose()}>
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
          {/* Name / Pattern */}
          {(editing?.mode === 'create' || editing?.mode === 'edit-trigger') && (
            <div className="flex flex-col gap-2">
              <Label>{editing.mode === 'create' ? '名稱' : '觸發詞'}</Label>
              <Input
                value={form.name}
                onChange={e => dispatch({ type: 'SET', field: 'name', value: e.target.value })}
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

          {/* Response */}
          {showResponseField && (
            <div className="flex flex-col gap-2">
              <Label>回應</Label>
              <Input
                ref={inputRef}
                value={form.response}
                onChange={e => dispatch({ type: 'SET', field: 'response', value: e.target.value })}
                placeholder={formIsCommand ? '回應文字 或 !指令名 $(query) 重導向' : '$(user) GG！'}
                className="font-mono text-sub"
              />
              <VariableInserter variables={commandVars} onInsert={insertText} />
            </div>
          )}

          {/* Enabled (edit only) */}
          {editing?.mode !== 'create' && (
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <Label>啟用</Label>
                <span className="text-label text-muted-foreground">關閉後不會回應</span>
              </div>
              <Switch
                checked={form.enabled}
                onCheckedChange={v => dispatch({ type: 'SET', field: 'enabled', value: v })}
              />
            </div>
          )}

          {/* Advanced toggle */}
          <button
            type="button"
            className="flex cursor-pointer items-center gap-2 text-sub text-muted-foreground transition-colors hover:text-foreground"
            onClick={() =>
              dispatch({ type: 'SET', field: 'showAdvanced', value: !form.showAdvanced })
            }
          >
            <Icon
              icon={form.showAdvanced ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
              wrapperClassName="size-3"
            />
            {form.showAdvanced ? '隱藏進階設定' : '顯示進階設定'}
          </button>

          {form.showAdvanced && (
            <div className="flex flex-col gap-card border-l-2 border-muted pl-page">
              {/* Aliases — command only */}
              {(isCreatingCommand || isEditingCommand) && (
                <div className="flex flex-col gap-2">
                  <Label>別名</Label>
                  <Input
                    value={form.aliases}
                    onChange={e =>
                      dispatch({ type: 'SET', field: 'aliases', value: e.target.value })
                    }
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
                      value={form.matchType}
                      onValueChange={v =>
                        dispatch({
                          type: 'SET',
                          field: 'matchType',
                          value: v as TriggerConfig['match_type'],
                        })
                      }
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
                    <Switch
                      checked={form.caseSensitive}
                      onCheckedChange={v =>
                        dispatch({ type: 'SET', field: 'caseSensitive', value: v })
                      }
                    />
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
                    value={form.priority}
                    onChange={e =>
                      dispatch({ type: 'SET', field: 'priority', value: e.target.value })
                    }
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
                  value={form.cooldown}
                  onChange={e =>
                    dispatch({ type: 'SET', field: 'cooldown', value: e.target.value })
                  }
                  placeholder={showTriggerFields ? '建議 30' : `預設: ${defaults.default_cooldown}`}
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
                <Select
                  value={form.role}
                  onValueChange={v => dispatch({ type: 'SET', field: 'role', value: v })}
                >
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

          {form.saveError && <p className="text-label text-destructive">{form.saveError}</p>}
        </div>

        <SheetFooter className="shrink-0 flex-row gap-2">
          {canDelete && (
            <Button variant="destructive" onClick={handleDelete}>
              <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
              刪除
            </Button>
          )}
          <div className="flex-1" />
          <SheetClose asChild>
            <Button variant="outline">取消</Button>
          </SheetClose>
          <Button onClick={handleSave} disabled={form.saving}>
            {form.saving ? '儲存中...' : '儲存'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
