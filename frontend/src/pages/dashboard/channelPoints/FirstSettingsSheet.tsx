import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { type RedemptionConfig, updateFirstRedemptionSettings } from '@/api/events'
import { Spinner } from '@/components/primitives'
import { TemplatePartsPreview } from '@/components/TemplatePartsPreview'
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
import { renderTemplateParts } from '@/lib/templateParts'
import { toastApiError } from '@/lib/toast-error'
import { cn } from '@/lib/utils'

const TWITCH_MESSAGE_LIMIT = 500

// Same legend as events/TemplatePreview — first_message shares the backend's
// render_template (event_render.py), [[ ]] segments included.
const PREVIEW_LEGEND = (
  <>
    <span className="text-primary">紫色</span>為變數代入值；
    <span className="line-through">刪除線</span>片段是 <span className="font-mono">[[ ]]</span>{' '}
    內變數無值、實際不顯示的部分。
  </>
)

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

// Twitch's fixed /announce palette (no public hex spec) — swatch values are
// close visual approximations for the picker, not the exact chat rendering.
const ANNOUNCE_COLORS: {
  value: string
  label: string
  swatchClassName?: string
  swatch?: string
}[] = [
  { value: 'primary', label: '預設色', swatchClassName: 'bg-primary' },
  { value: 'blue', label: '藍色', swatch: '#1E69FF' },
  { value: 'green', label: '綠色', swatch: '#00AD03' },
  { value: 'orange', label: '橘色', swatch: '#FF7C00' },
  { value: 'purple', label: '紫色', swatch: '#9C3EE8' },
]

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
  const previewParts = useMemo(() => renderTemplateParts(message, PREVIEW_VALUES), [message])

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
            <TemplatePartsPreview
              parts={previewParts}
              limit={TWITCH_MESSAGE_LIMIT}
              legend={PREVIEW_LEGEND}
            />
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
                    <span
                      aria-hidden
                      className={cn('size-3 shrink-0 rounded-full', color.swatchClassName)}
                      style={color.swatch ? { backgroundColor: color.swatch } : undefined}
                    />
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
