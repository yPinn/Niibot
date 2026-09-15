import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { type RedemptionConfig, updateFirstRedemptionSettings } from '@/api/events'
import { Spinner } from '@/components/primitives'
import {
  Button,
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
  Textarea,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useInputInsert } from '@/hooks/useInputInsert'
import { toastApiError } from '@/lib/toast-error'

interface FirstSettingsSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: RedemptionConfig | undefined
  onSaved: (updated: RedemptionConfig) => void
}

const DEFAULT_FIRST_MESSAGE = '$(@user) 恭喜你搶到沙發！'

const FIRST_VARIABLES = [
  { var: '$(@user)', desc: '帶 @ 的觀眾顯示名稱' },
  { var: '$(user)', desc: '不帶 @ 的觀眾顯示名稱' },
]

const PREVIEW_VALUES: Record<string, string> = {
  '@user': '@Viewer',
  user: 'Viewer',
}

const ANNOUNCE_COLORS = [
  { value: 'primary', label: '預設色' },
  { value: 'blue', label: '藍色' },
  { value: 'green', label: '綠色' },
  { value: 'orange', label: '橘色' },
  { value: 'purple', label: '紫色' },
]

function renderPreview(template: string): string {
  return template.replace(/\$\(([^)]+)\)/g, (token, name: string) => PREVIEW_VALUES[name] ?? token)
}

export function FirstSettingsSheet({
  open,
  onOpenChange,
  config,
  onSaved,
}: FirstSettingsSheetProps) {
  const [message, setMessage] = useState('')
  const [announceColor, setAnnounceColor] = useState('primary')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !config) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMessage(config.first_message)
    setAnnounceColor(config.first_announce_color)
  }, [open, config])

  const { inputRef, insertText } = useInputInsert<HTMLTextAreaElement>(message, setMessage)

  const handleSave = async () => {
    if (!message.trim()) return
    setSaving(true)
    try {
      const updated = await updateFirstRedemptionSettings({
        message,
        announce_color: announceColor,
      })
      toast.success('本日頭香設定已儲存')
      onSaved(updated)
      onOpenChange(false)
    } catch (error) {
      toastApiError(error, '儲存本日頭香設定失敗')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-section sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>本日頭香設定</SheetTitle>
          <SheetDescription>自訂當日第一位兌換觀眾收到的公告文字與顏色。</SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-card overflow-y-auto px-page pb-page">
          <section className="space-y-3" aria-labelledby="first-message-label">
            <div className="flex items-center justify-between gap-2">
              <Label id="first-message-label" htmlFor="first-message">
                公告訊息
              </Label>
              <Button variant="ghost" size="sm" onClick={() => setMessage(DEFAULT_FIRST_MESSAGE)}>
                恢復預設
              </Button>
            </div>
            <Textarea
              id="first-message"
              ref={inputRef}
              value={message}
              maxLength={300}
              rows={3}
              className="font-mono text-sub"
              onChange={event => setMessage(event.target.value)}
            />
            <VariableInserter variables={FIRST_VARIABLES} onInsert={insertText} />
            <div className="space-y-1.5">
              <p className="text-label text-muted-foreground">預覽</p>
              <div className="rounded-md border bg-muted/40 px-3 py-2 text-sub wrap-break-word">
                {message ? renderPreview(message) : '（訊息模板為空）'}
              </div>
            </div>
          </section>

          <section className="space-y-2 border-t pt-card" aria-labelledby="first-color-label">
            <Label id="first-color-label" htmlFor="first-color">
              公告顏色
            </Label>
            <Select value={announceColor} onValueChange={setAnnounceColor}>
              <SelectTrigger id="first-color" aria-label="公告顏色" className="w-full max-w-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ANNOUNCE_COLORS.map(color => (
                  <SelectItem key={color.value} value={color.value}>
                    {color.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </section>
        </div>

        <SheetFooter className="shrink-0 flex-row justify-end gap-2">
          <SheetClose asChild>
            <Button variant="outline">取消</Button>
          </SheetClose>
          <Button onClick={() => void handleSave()} disabled={saving || !message.trim()}>
            {saving && <Spinner className="mr-1.5" />}
            儲存設定
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
