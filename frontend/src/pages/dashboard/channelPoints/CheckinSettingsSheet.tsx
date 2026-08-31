import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import { type CheckinSettings, getCheckinSettings, updateCheckinSettings } from '@/api/checkin'
import { Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
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
  Skeleton,
  Textarea,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useInputInsert } from '@/hooks/useInputInsert'
import { toastApiError } from '@/lib/toast-error'

interface CheckinSettingsSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface CheckinForm {
  timezone: string
  successTemplate: string
  duplicateTemplate: string
}

const EMPTY_FORM: CheckinForm = {
  timezone: '',
  successTemplate: '',
  duplicateTemplate: '',
}

const CHECKIN_VARIABLES = [
  { var: '$(@user)', desc: '帶 @ 的觀眾顯示名稱' },
  { var: '$(user)', desc: '不帶 @ 的觀眾顯示名稱' },
  { var: '$(count)', desc: '這個頻道的累積簽到天數' },
  { var: '$(date)', desc: '依設定時區計算的簽到日期' },
]

const PREVIEW_VALUES: Record<string, string> = {
  '@user': '@Viewer',
  user: 'Viewer',
  count: '12',
  date: '2026-08-31',
}

function toForm(settings: CheckinSettings): CheckinForm {
  return {
    timezone: settings.timezone,
    successTemplate: settings.success_template,
    duplicateTemplate: settings.duplicate_template,
  }
}

function renderPreview(template: string): string {
  return template.replace(/\$\(([^)]+)\)/g, (token, name: string) => PREVIEW_VALUES[name] ?? token)
}

function MessagePreview({ label, template }: { label: string; template: string }) {
  return (
    <div className="space-y-1.5">
      <p className="text-label text-muted-foreground">{label}預覽</p>
      <div className="rounded-md border bg-muted/40 px-3 py-2 text-sub wrap-break-word">
        {template ? renderPreview(template) : '（訊息模板為空）'}
      </div>
    </div>
  )
}

export function CheckinSettingsSheet({ open, onOpenChange }: CheckinSettingsSheetProps) {
  const [form, setForm] = useState<CheckinForm>(EMPTY_FORM)
  const [loading, setLoading] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setLoadFailed(false)
    setValidationError(null)
    try {
      setForm(toForm(await getCheckinSettings()))
    } catch (error) {
      setLoadFailed(true)
      toastApiError(error, '載入簽到設定失敗')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSettings()
  }, [loadSettings, open])

  const updateForm = (field: keyof CheckinForm, value: string) => {
    setForm(current => ({ ...current, [field]: value }))
    setValidationError(null)
  }

  const { inputRef: successInputRef, insertText: insertSuccessVariable } =
    useInputInsert<HTMLTextAreaElement>(form.successTemplate, value =>
      updateForm('successTemplate', value)
    )
  const { inputRef: duplicateInputRef, insertText: insertDuplicateVariable } =
    useInputInsert<HTMLTextAreaElement>(form.duplicateTemplate, value =>
      updateForm('duplicateTemplate', value)
    )

  const handleSave = async () => {
    const timezone = form.timezone.trim()
    if (!timezone || !form.successTemplate.trim() || !form.duplicateTemplate.trim()) {
      setValidationError('時區與兩種訊息模板都不可留空。')
      return
    }

    setSaving(true)
    setValidationError(null)
    try {
      const updated = await updateCheckinSettings({
        timezone,
        success_template: form.successTemplate,
        duplicate_template: form.duplicateTemplate,
      })
      setForm(toForm(updated))
      toast.success('Check-in settings 已儲存')
      onOpenChange(false)
    } catch (error) {
      toastApiError(error, '儲存簽到設定失敗')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-section sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Check-in settings</SheetTitle>
          <SheetDescription>
            時區與回覆模板由聊天指令與 Twitch 點數簽到共用；獎勵綁定仍在表格管理。
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-48 w-full" />
              <Skeleton className="h-48 w-full" />
            </div>
          ) : loadFailed ? (
            <Alert variant="destructive">
              <Icon icon="fa-solid fa-circle-exclamation" />
              <AlertTitle>簽到設定載入失敗</AlertTitle>
              <AlertDescription>
                <Button size="sm" variant="outline" onClick={() => void loadSettings()}>
                  重新載入
                </Button>
              </AlertDescription>
            </Alert>
          ) : (
            <>
              <section className="space-y-2" aria-labelledby="checkin-timezone-label">
                <Label id="checkin-timezone-label" htmlFor="checkin-timezone">
                  時區
                </Label>
                <Input
                  id="checkin-timezone"
                  aria-label="時區"
                  value={form.timezone}
                  maxLength={64}
                  placeholder="Asia/Taipei"
                  onChange={event => updateForm('timezone', event.target.value)}
                />
                <p className="text-label text-muted-foreground">
                  使用 IANA 時區名稱；每日簽到會依此時區跨日，例如 Asia/Taipei。
                </p>
              </section>

              <section className="space-y-3 border-t pt-card" aria-labelledby="success-label">
                <div className="space-y-1">
                  <Label id="success-label" htmlFor="checkin-success-template">
                    簽到成功訊息
                  </Label>
                  <p className="text-label text-muted-foreground">當今天第一次簽到成功時回覆。</p>
                </div>
                <Textarea
                  id="checkin-success-template"
                  ref={successInputRef}
                  value={form.successTemplate}
                  maxLength={500}
                  rows={3}
                  className="font-mono text-sub"
                  onChange={event => updateForm('successTemplate', event.target.value)}
                />
                <VariableInserter variables={CHECKIN_VARIABLES} onInsert={insertSuccessVariable} />
                <MessagePreview label="成功訊息" template={form.successTemplate} />
              </section>

              <section className="space-y-3 border-t pt-card" aria-labelledby="duplicate-label">
                <div className="space-y-1">
                  <Label id="duplicate-label" htmlFor="checkin-duplicate-template">
                    已簽到訊息
                  </Label>
                  <p className="text-label text-muted-foreground">
                    同一位觀眾在同一天重複簽到時回覆，不會增加累積天數。
                  </p>
                </div>
                <Textarea
                  id="checkin-duplicate-template"
                  ref={duplicateInputRef}
                  value={form.duplicateTemplate}
                  maxLength={500}
                  rows={3}
                  className="font-mono text-sub"
                  onChange={event => updateForm('duplicateTemplate', event.target.value)}
                />
                <VariableInserter
                  variables={CHECKIN_VARIABLES}
                  onInsert={insertDuplicateVariable}
                />
                <MessagePreview label="重複訊息" template={form.duplicateTemplate} />
              </section>

              {validationError && (
                <p className="text-label text-destructive" role="alert">
                  {validationError}
                </p>
              )}
            </>
          )}
        </div>

        <SheetFooter className="shrink-0 flex-row justify-end gap-2">
          <SheetClose asChild>
            <Button variant="outline">取消</Button>
          </SheetClose>
          <Button
            onClick={() => void handleSave()}
            disabled={
              loading ||
              loadFailed ||
              saving ||
              !form.timezone ||
              !form.successTemplate ||
              !form.duplicateTemplate
            }
          >
            {saving && <Spinner className="mr-1.5" />}
            儲存設定
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
