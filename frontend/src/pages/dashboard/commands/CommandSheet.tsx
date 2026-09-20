import { useEffect, useReducer, useState } from 'react'
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
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { EmoteInserter } from '@/components/EmoteInserter'
import { Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  Button,
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
  Textarea,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useChannelEmotes } from '@/hooks/useChannelEmotes'
import { useInputInsert } from '@/hooks/useInputInsert'
import { toastApiError } from '@/lib/toast-error'

import { AUDIENCE_LABELS, EDITABLE_COMMANDS, PUBLIC_ROLE_LABELS, ROLE_LABELS } from './constants'
import type { EditingState } from './types'

interface FormState {
  name: string
  response: string
  cooldown: string
  role: string
  aliases: string
  triggerAliases: string
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
  triggerAliases: '',
  matchType: 'startswith',
  caseSensitive: false,
  priority: '0',
  enabled: true,
  showAdvanced: false,
  saving: false,
  saveError: null,
}

function parseCooldown(value: string): number | null {
  if (value.trim() === '') return null
  const n = parseInt(value, 10)
  if (isNaN(n) || n < 0) return null
  return n
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

/** Keep in sync with backend MAX_RESPONSE_LENGTH (api/core/constants.py). */
const MAX_RESPONSE_LENGTH = 450

const COMMAND_VARS = [
  { var: '$(user)', desc: '使用者名稱' },
  { var: '$(touser)', desc: '第一個參數，沒有就用發話者' },
  { var: '$(query)', desc: '使用者輸入' },
  { var: '$(1)', desc: '第 1 個參數' },
  { var: '$(1:)', desc: '第 1 個參數之後的全部內容' },
  { var: '$(1|預設值)', desc: '第 1 個參數，沒有時使用預設值' },
  { var: '$(queryescape)', desc: '將使用者輸入編碼為網址查詢值' },
  { var: '$(pathescape)', desc: '將使用者輸入編碼為網址路徑' },
  { var: '$(channel)', desc: '頻道名稱' },
  { var: '$(count)', desc: '指令使用次數' },
  { var: '$(random 1,100)', desc: '隨機數字' },
  { var: '$(pick a,b,c)', desc: '隨機選擇' },
]

export interface CommandSheetProps {
  open: boolean
  editing: EditingState | null
  defaults: ChannelDefaults
  onSaved: (result: { commands?: CommandConfig[]; triggers?: TriggerConfig[] }) => void
  onDeleted: (kind: 'command' | 'trigger', name: string) => void
  onClose: () => void
}

export function CommandSheet({
  open,
  editing,
  defaults,
  onSaved,
  onDeleted,
  onClose,
}: CommandSheetProps) {
  const [form, dispatch] = useReducer(formReducer, initialForm)
  const [confirmDelete, setConfirmDelete] = useState(false)

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
          showAdvanced: false,
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
          triggerAliases: t.aliases || '',
          showAdvanced: false,
        },
      })
    }
  }, [editing])

  const { inputRef, insertText } = useInputInsert<HTMLTextAreaElement>(form.response, newVal =>
    dispatch({ type: 'SET', field: 'response', value: newVal })
  )
  const {
    emotes,
    otherChannels,
    loading: emotesLoading,
    error: emotesError,
  } = useChannelEmotes(open)

  const formIsCommand = form.name.startsWith('!')
  const isEditingTrigger = editing?.mode === 'edit-trigger'
  const isCreatingTrigger = editing?.mode === 'create' && !formIsCommand
  const showTriggerFields = isEditingTrigger || isCreatingTrigger
  const isEditingCommand = editing?.mode === 'edit-command'
  const isCreatingCommand = editing?.mode === 'create' && formIsCommand
  const canDelete =
    (editing?.mode === 'edit-command' && editing.command.command_type === 'custom') ||
    editing?.mode === 'edit-trigger'

  let sheetTitle = ''
  if (editing) {
    if (editing.mode === 'create') sheetTitle = formIsCommand ? '新增自訂指令' : '新增自動回應'
    else if (editing.mode === 'edit-command') sheetTitle = `編輯 !${editing.command.command_name}`
    else sheetTitle = `編輯 ${editing.trigger.trigger_name}`
  }

  const handleSave = async () => {
    if (!editing) return

    // Synchronous validation before disabling the save button
    if (editing.mode === 'create') {
      if (!form.name.trim() || !form.response.trim()) {
        dispatch({ type: 'SAVE_ERROR', msg: '名稱與回應不可為空' })
        return
      }
      if (formIsCommand && !form.name.slice(1).trim()) {
        dispatch({ type: 'SAVE_ERROR', msg: '指令名稱不可為空' })
        return
      }
    }

    if (form.response.trim().length > MAX_RESPONSE_LENGTH) {
      dispatch({ type: 'SAVE_ERROR', msg: `回應內容上限 ${MAX_RESPONSE_LENGTH} 字` })
      return
    }

    dispatch({ type: 'SAVING' })
    try {
      if (editing.mode === 'create') {
        if (formIsCommand) {
          const cmdName = form.name.slice(1).trim()
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
            aliases: form.triggerAliases.trim() || null,
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
          aliases: form.triggerAliases.trim() || null,
        })
        onSaved({ triggers: [updated] })
      }
      toast.success(editing.mode === 'create' ? '建立成功' : '已儲存變更')
      onClose()
    } catch (e) {
      const msg = e instanceof Error ? e.message : '儲存失敗'
      dispatch({ type: 'SAVE_ERROR', msg })
      toastApiError(e, '儲存失敗')
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
    } catch (e) {
      toastApiError(e, '刪除失敗')
    }
  }

  const showResponseField =
    editing?.mode === 'create' ||
    (isEditingCommand &&
      (editing.command.command_type === 'custom' ||
        EDITABLE_COMMANDS.includes(editing.command.command_name))) ||
    isEditingTrigger

  const builtinCommand =
    editing?.mode === 'edit-command' && editing.command.command_type === 'builtin'
      ? editing.command
      : null
  const publicRoleLabel = PUBLIC_ROLE_LABELS[form.role]
  const showsOnPublicPage = builtinCommand?.audience === 'viewer' && publicRoleLabel

  return (
    <Sheet open={open} onOpenChange={o => !o && onClose()}>
      <SheetContent className="gap-section">
        <SheetHeader>
          <SheetTitle>{sheetTitle}</SheetTitle>
          <SheetDescription>
            {editing?.mode === 'create'
              ? formIsCommand
                ? '以 ! 開頭建立指令；不加 ! 則建立自動回應'
                : '偵測到關鍵字時自動回應；加上 ! 可改為建立指令'
              : showTriggerFields
                ? '修改自動回應設定'
                : '修改指令設定'}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
          {builtinCommand && (
            <section
              aria-labelledby="command-feature-title"
              className="space-y-3 rounded-lg bg-muted/40 p-page"
            >
              <div className="space-y-1">
                <h3 id="command-feature-title" className="text-sub font-semibold">
                  指令功能
                </h3>
                <p className="text-sub leading-relaxed text-muted-foreground">
                  {builtinCommand.detail}
                </p>
              </div>

              <dl className="grid grid-cols-[5rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-label">
                <dt className="text-muted-foreground">用途</dt>
                <dd>{builtinCommand.description}</dd>

                <dt className="text-muted-foreground">使用方式</dt>
                <dd className="font-mono">
                  {builtinCommand.usage}
                  {builtinCommand.aliases &&
                    ` · ${builtinCommand.aliases
                      .split(',')
                      .map(alias => `!${alias.trim()}`)
                      .join(' · ')}`}
                </dd>

                <dt className="text-muted-foreground">適用身分</dt>
                <dd>
                  {builtinCommand.audience
                    ? AUDIENCE_LABELS[builtinCommand.audience]
                    : ROLE_LABELS[form.role]}
                </dd>

                <dt className="text-muted-foreground">公開指令頁</dt>
                <dd>
                  {showsOnPublicPage
                    ? `顯示於公開指令頁 · ${publicRoleLabel}`
                    : '不顯示於公開指令頁'}
                </dd>
              </dl>

              {builtinCommand.preview_input && builtinCommand.preview_output && (
                <div className="space-y-2 border-t border-border/70 pt-3">
                  <div>
                    <h4 className="text-label font-semibold">效果預覽</h4>
                    <p className="text-label text-muted-foreground">示意內容，不會實際執行指令</p>
                  </div>

                  <div aria-label="聊天室效果預覽" className="divide-y divide-border/60">
                    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 py-2 text-label">
                      <span className="font-semibold text-muted-foreground">小霓</span>
                      <code className="break-words text-foreground">
                        {builtinCommand.preview_input}
                      </code>
                    </div>
                    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 py-2 text-label">
                      <span className="font-semibold text-primary">Niibot</span>
                      <p className="break-words leading-relaxed">{builtinCommand.preview_output}</p>
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}

          {/* ── Name / Pattern ── */}
          {(editing?.mode === 'create' || editing?.mode === 'edit-trigger') && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="cmd-name">{showTriggerFields ? '觸發詞' : '指令名稱'}</Label>
              <Input
                id="cmd-name"
                value={form.name}
                onChange={e => dispatch({ type: 'SET', field: 'name', value: e.target.value })}
                placeholder={showTriggerFields ? '觸發關鍵字' : '!指令名稱'}
                className="font-mono"
                autoFocus
              />
              {editing.mode === 'create' && (
                <span className="text-label text-muted-foreground">
                  {formIsCommand ? '聊天室輸入 !名稱 觸發' : '訊息包含此關鍵字時觸發'}
                </span>
              )}
            </div>
          )}

          {/* ── Match type — trigger primary field ── */}
          {showTriggerFields && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="cmd-match-type">比對方式</Label>
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
                <SelectTrigger id="cmd-match-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectItem value="contains">包含關鍵字</SelectItem>
                  <SelectItem value="startswith">以關鍵字開頭</SelectItem>
                  <SelectItem value="exact">完全相符</SelectItem>
                  <SelectItem value="regex">正規表達式</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* ── Response ── */}
          {showResponseField && (
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between">
                <Label htmlFor="cmd-response">回應內容</Label>
                <span
                  className={
                    form.response.length > MAX_RESPONSE_LENGTH
                      ? 'text-label text-destructive'
                      : 'text-label text-muted-foreground'
                  }
                >
                  {form.response.length} / {MAX_RESPONSE_LENGTH}
                </span>
              </div>
              <Textarea
                id="cmd-response"
                ref={inputRef}
                value={form.response}
                onChange={e => dispatch({ type: 'SET', field: 'response', value: e.target.value })}
                placeholder={showTriggerFields ? '$(user) GG！' : '$(user) 你好！'}
                className="font-mono text-sub"
              />
              {form.response.length > MAX_RESPONSE_LENGTH && (
                <p className="text-label text-destructive">
                  超過 {MAX_RESPONSE_LENGTH} 字，變數展開後會被 Twitch 截斷
                </p>
              )}
              <VariableInserter variables={COMMAND_VARS} onInsert={insertText} />
              <EmoteInserter
                emotes={emotes}
                otherChannels={otherChannels}
                onInsert={insertText}
                loading={emotesLoading}
                error={emotesError}
              />
            </div>
          )}

          {/* ── Enabled (edit only) ── */}
          {editing?.mode !== 'create' && (
            <SettingRow title="啟用" description="關閉後不會回應">
              <Switch
                aria-label="啟用"
                checked={form.enabled}
                onCheckedChange={v => dispatch({ type: 'SET', field: 'enabled', value: v })}
              />
            </SettingRow>
          )}

          <Button
            variant="ghost"
            size="sm"
            className="w-fit px-0 text-muted-foreground hover:text-foreground hover:bg-transparent"
            onClick={() =>
              dispatch({ type: 'SET', field: 'showAdvanced', value: !form.showAdvanced })
            }
          >
            <Icon
              icon={form.showAdvanced ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
              wrapperClassName="size-3"
            />
            {form.showAdvanced ? '隱藏進階設定' : '顯示進階設定'}
          </Button>

          {form.showAdvanced && (
            <div className="flex flex-col gap-card border-l-2 border-muted pl-page">
              {/* Aliases — command only */}
              {(isCreatingCommand || isEditingCommand) && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="cmd-aliases">別名</Label>
                  <Input
                    id="cmd-aliases"
                    value={form.aliases}
                    onChange={e =>
                      dispatch({ type: 'SET', field: 'aliases', value: e.target.value })
                    }
                    placeholder="hi,hey,hello"
                    className="font-mono text-sub"
                  />
                  <span className="text-label text-muted-foreground">
                    多個用逗號分隔，自動加 ! 前綴
                  </span>
                </div>
              )}

              {/* Trigger aliases — trigger only */}
              {showTriggerFields && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="cmd-trigger-aliases">觸發別名</Label>
                  <Input
                    id="cmd-trigger-aliases"
                    value={form.triggerAliases}
                    onChange={e =>
                      dispatch({ type: 'SET', field: 'triggerAliases', value: e.target.value })
                    }
                    placeholder="gg,GG,好耶"
                    className="font-mono text-sub"
                  />
                  <span className="text-label text-muted-foreground">
                    多個用逗號分隔，任一符合即觸發
                  </span>
                </div>
              )}

              {/* Case sensitive — trigger only, hidden for regex (regex handles its own case via flags) */}
              {showTriggerFields && form.matchType !== 'regex' && (
                <SettingRow title="區分大小寫" description="開啟後 GG 與 gg 視為不同">
                  <Switch
                    aria-label="區分大小寫"
                    checked={form.caseSensitive}
                    onCheckedChange={v =>
                      dispatch({ type: 'SET', field: 'caseSensitive', value: v })
                    }
                  />
                </SettingRow>
              )}

              {/* Priority — trigger only */}
              {showTriggerFields && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="cmd-priority">優先度</Label>
                  <Input
                    id="cmd-priority"
                    type="number"
                    step={1}
                    value={form.priority}
                    onChange={e =>
                      dispatch({ type: 'SET', field: 'priority', value: e.target.value })
                    }
                    placeholder="0"
                    className="w-24"
                  />
                  <span className="text-label text-muted-foreground">越大越優先，預設 0</span>
                </div>
              )}

              {/* Cooldown */}
              <div className="flex flex-col gap-2">
                <Label htmlFor="cmd-cooldown">冷卻 (秒)</Label>
                <Input
                  id="cmd-cooldown"
                  type="number"
                  min={0}
                  step={5}
                  value={form.cooldown}
                  onChange={e =>
                    dispatch({ type: 'SET', field: 'cooldown', value: e.target.value })
                  }
                  placeholder={showTriggerFields ? '30' : String(defaults.default_cooldown)}
                  className="w-24"
                />
                <span className="text-label text-muted-foreground">
                  {showTriggerFields
                    ? '留空則無限制'
                    : `留空則套用頻道預設 (${defaults.default_cooldown}s)`}
                </span>
              </div>

              {/* Min Role */}
              <div className="flex flex-col gap-2">
                <Label htmlFor="cmd-role">最低權限</Label>
                <Select
                  value={form.role}
                  onValueChange={v => dispatch({ type: 'SET', field: 'role', value: v })}
                >
                  <SelectTrigger id="cmd-role" className="w-24">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper" className="w-24 min-w-0">
                    {Object.entries(ROLE_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <span className="text-label text-muted-foreground">低於此權限的使用者無法觸發</span>
              </div>
            </div>
          )}

          {form.saveError && <p className="text-label text-destructive">{form.saveError}</p>}
        </div>

        <SheetFooter className="shrink-0 flex-row gap-2">
          {canDelete && (
            <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
              <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
              刪除
            </Button>
          )}
          <div className="flex-1" />
          <SheetClose asChild>
            <Button variant="outline">取消</Button>
          </SheetClose>
          <Button onClick={handleSave} disabled={form.saving}>
            {form.saving && <Spinner className="mr-1.5" />}
            儲存
          </Button>
        </SheetFooter>
      </SheetContent>

      <DeleteConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="確定刪除？"
        description={
          editing?.mode === 'edit-trigger'
            ? `即將刪除自動回應「${editing.trigger.pattern}」，此操作無法還原。`
            : `即將刪除指令「!${editing?.mode === 'edit-command' ? editing.command.command_name : ''}」，此操作無法還原。`
        }
        onConfirm={handleDelete}
      />
    </Sheet>
  )
}
