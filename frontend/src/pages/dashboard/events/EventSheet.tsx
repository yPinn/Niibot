import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { type EventConfig, updateEventConfig } from '@/api/events'
import { Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Input,
  Label,
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
import { toastApiError } from '@/lib/toast-error'

import { EVENT_TYPE_NAMES, TEMPLATE_VARIABLES } from './constants'

interface EventSheetProps {
  event: EventConfig | null
  onClose: () => void
  onSaved: (updated: EventConfig) => void
}

export function EventSheet({ event, onClose, onSaved }: EventSheetProps) {
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
    useInputInsert<HTMLInputElement>(editTemplate, setEditTemplate)

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

  return (
    <Sheet open={!!event} onOpenChange={open => !open && onClose()}>
      <SheetContent className="gap-section">
        <SheetHeader>
          <SheetTitle>
            編輯 {event ? EVENT_TYPE_NAMES[event.event_type] || event.event_type : ''}
          </SheetTitle>
          <SheetDescription>設定此事件觸發時的自動回應訊息</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-card px-page">
          <div className="flex flex-col gap-2">
            <Label htmlFor="event-template">訊息模板</Label>
            <Input
              id="event-template"
              ref={templateInputRef}
              value={editTemplate}
              onChange={e => setEditTemplate(e.target.value)}
              placeholder="輸入回應訊息..."
              className="font-mono text-sub"
            />

            {event && TEMPLATE_VARIABLES[event.event_type] && (
              <VariableInserter
                variables={TEMPLATE_VARIABLES[event.event_type]}
                onInsert={insertVariable}
              />
            )}
          </div>

          {event?.event_type === 'raid' && (
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="flex items-center gap-1.5 text-sub font-medium leading-none">
                  自動推薦
                  <Badge variant="secondary" className="text-label">
                    需要管理員
                  </Badge>
                </span>
                <span className="text-label text-muted-foreground">
                  揪團時自動執行 /shoutout 展示對方頻道
                </span>
              </div>
              <Switch
                aria-label="自動推薦"
                checked={(editOptions.auto_shoutout as boolean) ?? true}
                onCheckedChange={v => setEditOptions(prev => ({ ...prev, auto_shoutout: v }))}
              />
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-0.5">
              <span className="text-sub font-medium leading-none">啟用</span>
              <span className="text-label text-muted-foreground">關閉後事件觸發時不會發送訊息</span>
            </div>
            <Switch aria-label="啟用" checked={editEnabled} onCheckedChange={setEditEnabled} />
          </div>
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
