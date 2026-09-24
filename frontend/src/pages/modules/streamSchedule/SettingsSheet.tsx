import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { getCheckinSettings } from '@/api/checkin'
import { type StreamScheduleSettings, updateStreamScheduleSettings } from '@/api/streamSchedule'
import { Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
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
  Switch,
} from '@/components/ui'
import { withCurrentTimezone } from '@/lib/timezones'
import { toastApiError } from '@/lib/toast-error'

interface SettingsSheetProps {
  open: boolean
  settings: StreamScheduleSettings | null
  onSaved: (settings: StreamScheduleSettings) => void
  onClose: () => void
}

/** Outer shell owns the Sheet's open state so its animation survives; the inner
 * form is keyed by `open` so it remounts fresh (from `settings` via a lazy
 * initializer) each time the sheet opens, instead of an effect syncing state. */
export function SettingsSheet({ open, settings, onSaved, onClose }: SettingsSheetProps) {
  return (
    <Sheet open={open} onOpenChange={o => !o && onClose()}>
      <SheetContent className="gap-section">
        {settings && (
          <SettingsSheetForm
            key={open ? 'open' : 'closed'}
            settings={settings}
            onSaved={onSaved}
            onClose={onClose}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}

interface SettingsSheetFormProps {
  settings: StreamScheduleSettings
  onSaved: (settings: StreamScheduleSettings) => void
  onClose: () => void
}

function SettingsSheetForm({ settings, onSaved, onClose }: SettingsSheetFormProps) {
  const [timezone, setTimezone] = useState(settings.timezone)
  const [enabled, setEnabled] = useState(settings.enabled)
  const [saving, setSaving] = useState(false)
  const [checkinTimezone, setCheckinTimezone] = useState<string | null>(null)

  useEffect(() => {
    // Best-effort — the check-in feature may not be configured, that's fine.
    getCheckinSettings()
      .then(s => setCheckinTimezone(s.timezone))
      .catch(() => setCheckinTimezone(null))
  }, [])

  const timezoneOptions = useMemo(() => withCurrentTimezone(timezone), [timezone])
  const showCheckinHint = checkinTimezone && checkinTimezone !== timezone

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await updateStreamScheduleSettings({ timezone, enabled })
      onSaved(updated)
      toast.success('排程設定已更新')
      onClose()
    } catch (e) {
      toastApiError(e, '更新排程設定失敗')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <SheetHeader>
        <SheetTitle>排程設定</SheetTitle>
        <SheetDescription>用來判斷「今天星期幾」，以及排程的開始、結束時間</SheetDescription>
      </SheetHeader>

      <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
        <div className="flex flex-col gap-2">
          <Label htmlFor="schedule-timezone">時區</Label>
          <Select value={timezone} onValueChange={setTimezone}>
            <SelectTrigger id="schedule-timezone" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {timezoneOptions.map(option => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {showCheckinHint && (
            <button
              type="button"
              className="flex w-fit items-center gap-1.5 text-label text-muted-foreground hover:text-foreground"
              onClick={() => setTimezone(checkinTimezone)}
            >
              <Icon icon="fa-solid fa-arrow-turn-down" wrapperClassName="size-3" />
              套用簽到系統目前的時區（{checkinTimezone}）
            </button>
          )}
        </div>

        <SettingRow title="啟用排程自動套用" description="關閉後不會自動套用任何排程的標題／分類">
          <Switch aria-label="啟用排程自動套用" checked={enabled} onCheckedChange={setEnabled} />
        </SettingRow>
      </div>

      <SheetFooter className="shrink-0 flex-row gap-2">
        <div className="flex-1" />
        <SheetClose asChild>
          <Button variant="outline">取消</Button>
        </SheetClose>
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Spinner className="mr-1.5" />}
          儲存
        </Button>
      </SheetFooter>
    </>
  )
}
