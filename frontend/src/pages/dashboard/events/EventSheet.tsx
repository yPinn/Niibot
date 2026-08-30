import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { type EventConfig, type EventDefinition, updateEventConfig } from '@/api/events'
import { Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  Button,
  Label,
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
import { useInputInsert } from '@/hooks/useInputInsert'
import { toastApiError } from '@/lib/toast-error'

import { TemplatePreview } from './TemplatePreview'

interface EventSheetProps {
  event: EventConfig | null
  definition: EventDefinition | undefined
  onClose: () => void
  onSaved: (updated: EventConfig) => void
}

export function EventSheet({ event, definition, onClose, onSaved }: EventSheetProps) {
  const [editTemplate, setEditTemplate] = useState('')
  const [editEnabled, setEditEnabled] = useState(true)
  const [editOptions, setEditOptions] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!event) return
    // Seed the form when a row is opened for editing. eslint-disable per the
    // repo convention for "sync local form state from the selected item".
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEditTemplate(event.message_template)
    setEditEnabled(event.enabled)
    setEditOptions(event.options ?? {})
  }, [event])

  const { inputRef: templateInputRef, insertText: insertVariable } =
    useInputInsert<HTMLTextAreaElement>(editTemplate, setEditTemplate)

  const handleSave = async () => {
    if (!event) return
    setSaving(true)
    try {
      const updated = await updateEventConfig(event.event_type, {
        message_template: editTemplate,
        enabled: editEnabled,
        options: editOptions,
      })
      onSaved(updated)
      toast.success('事件設定已儲存')
    } catch (e) {
      toastApiError(e, '儲存事件設定失敗')
    } finally {
      setSaving(false)
    }
  }

  const variableChips =
    definition?.variables.map(v => ({ var: `$(${v.name})`, desc: v.description })) ?? []

  return (
    <Sheet open={!!event} onOpenChange={open => !open && onClose()}>
      <SheetContent className="gap-section">
        <SheetHeader>
          <SheetTitle>編輯 {definition?.display_name ?? event?.event_type ?? ''}</SheetTitle>
          <SheetDescription>設定此事件觸發時的自動回應訊息</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-card px-page">
          <div className="flex flex-col gap-2">
            <Label htmlFor="event-template">訊息模板</Label>
            <Textarea
              id="event-template"
              ref={templateInputRef}
              value={editTemplate}
              onChange={e => setEditTemplate(e.target.value)}
              placeholder="輸入回應訊息..."
              rows={2}
              className="min-h-16 font-mono text-sub"
            />

            {variableChips.length > 0 && (
              <VariableInserter variables={variableChips} onInsert={insertVariable} />
            )}
          </div>

          {definition && (
            <TemplatePreview template={editTemplate} variables={definition.variables} />
          )}

          {definition?.options_schema.map(opt =>
            opt.type !== 'boolean' ? null : (
              <SettingRow key={opt.key} title={opt.label} description={opt.description}>
                <Switch
                  aria-label={opt.label}
                  checked={(editOptions[opt.key] as boolean) ?? opt.default}
                  onCheckedChange={v => setEditOptions(prev => ({ ...prev, [opt.key]: v }))}
                />
              </SettingRow>
            )
          )}

          <SettingRow title="啟用" description="關閉後事件觸發時不會發送訊息">
            <Switch aria-label="啟用" checked={editEnabled} onCheckedChange={setEditEnabled} />
          </SettingRow>
        </div>

        <SheetFooter className="flex-row justify-end gap-2">
          <SheetClose asChild>
            <Button variant="outline">取消</Button>
          </SheetClose>
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Spinner className="mr-1.5" />}
            儲存
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
