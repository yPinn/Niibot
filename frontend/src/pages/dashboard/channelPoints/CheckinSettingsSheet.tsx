import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type CheckinLeaderboardEntry,
  type CheckinSettings,
  getCheckinLeaderboard,
  getCheckinSettings,
  updateCheckinSettings,
} from '@/api/checkin'
import { EmoteInserter } from '@/components/EmoteInserter'
import { Icon, Spinner } from '@/components/primitives'
import { TemplatePartsPreview } from '@/components/TemplatePartsPreview'
import {
  Alert,
  AlertDescription,
  AlertTitle,
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
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from '@/components/ui'
import { VariableInserter } from '@/components/VariableInserter'
import { useChannelEmotes } from '@/hooks/useChannelEmotes'
import { useInputInsert } from '@/hooks/useInputInsert'
import { tokenizeVars } from '@/lib/templateParts'
import { toastApiError } from '@/lib/toast-error'

import { CheckinLeaderboard } from './CheckinLeaderboard'

// Curated IANA zones, not a free-text field — a typo here silently breaks
// the daily check-in boundary. Picking from a list also keeps DST handling
// correct (ZoneInfo), which a raw UTC-offset number can't do.
const TIMEZONE_OPTIONS: { value: string; label: string }[] = [
  { value: 'Asia/Taipei', label: '台北（UTC+8）' },
  { value: 'Asia/Hong_Kong', label: '香港（UTC+8）' },
  { value: 'Asia/Shanghai', label: '上海（UTC+8）' },
  { value: 'Asia/Singapore', label: '新加坡（UTC+8）' },
  { value: 'Asia/Manila', label: '馬尼拉（UTC+8）' },
  { value: 'Asia/Tokyo', label: '東京（UTC+9）' },
  { value: 'Asia/Seoul', label: '首爾（UTC+9）' },
  { value: 'Asia/Bangkok', label: '曼谷（UTC+7）' },
  { value: 'Asia/Kolkata', label: '新德里（UTC+5:30）' },
  { value: 'Asia/Dubai', label: '杜拜（UTC+4）' },
  { value: 'Europe/Moscow', label: '莫斯科（UTC+3）' },
  { value: 'Europe/Berlin', label: '柏林（UTC+1/+2）' },
  { value: 'Europe/Paris', label: '巴黎（UTC+1/+2）' },
  { value: 'Europe/London', label: '倫敦（UTC+0/+1）' },
  { value: 'UTC', label: 'UTC（UTC+0）' },
  { value: 'America/New_York', label: '紐約（UTC-5/-4）' },
  { value: 'America/Chicago', label: '芝加哥（UTC-6/-5）' },
  { value: 'America/Denver', label: '丹佛（UTC-7/-6）' },
  { value: 'America/Los_Angeles', label: '洛杉磯（UTC-8/-7）' },
  { value: 'Australia/Sydney', label: '雪梨（UTC+10/+11）' },
  { value: 'Pacific/Auckland', label: '奧克蘭（UTC+12/+13）' },
]

interface CheckinSettingsSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface CheckinForm {
  timezone: string
  successTemplate: string
  duplicateTemplate: string
  replyDelaySeconds: number
}

const EMPTY_FORM: CheckinForm = {
  timezone: '',
  successTemplate: '',
  duplicateTemplate: '',
  replyDelaySeconds: 0,
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
    replyDelaySeconds: settings.reply_delay_seconds,
  }
}

const TWITCH_MESSAGE_LIMIT = 500

// Check-in's backend renderer (render_checkin_template) only does flat
// $(var) substitution — no [[ ]] segments — so no "dropped" legend needed.
const PREVIEW_LEGEND = (
  <>
    <span className="text-primary">紫色</span>為變數代入值。
  </>
)

export function CheckinSettingsSheet({ open, onOpenChange }: CheckinSettingsSheetProps) {
  const [form, setForm] = useState<CheckinForm>(EMPTY_FORM)
  const [loading, setLoading] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [leaderboard, setLeaderboard] = useState<CheckinLeaderboardEntry[]>([])
  const [leaderboardLoading, setLeaderboardLoading] = useState(false)
  const [leaderboardLoadFailed, setLeaderboardLoadFailed] = useState(false)

  // Existing settings may hold an IANA zone outside the curated list (typed
  // in before this became a dropdown) — keep it selectable instead of
  // silently resetting the field to blank.
  const timezoneOptions = useMemo(() => {
    if (!form.timezone || TIMEZONE_OPTIONS.some(option => option.value === form.timezone)) {
      return TIMEZONE_OPTIONS
    }
    return [{ value: form.timezone, label: form.timezone }, ...TIMEZONE_OPTIONS]
  }, [form.timezone])

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

  const loadLeaderboard = useCallback(async () => {
    setLeaderboardLoading(true)
    setLeaderboardLoadFailed(false)
    try {
      setLeaderboard(await getCheckinLeaderboard())
    } catch {
      setLeaderboardLoadFailed(true)
    } finally {
      setLeaderboardLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSettings()
    void loadLeaderboard()
  }, [loadLeaderboard, loadSettings, open])

  const updateForm = (field: keyof Omit<CheckinForm, 'replyDelaySeconds'>, value: string) => {
    setForm(current => ({ ...current, [field]: value }))
    setValidationError(null)
  }

  const updateReplyDelay = (value: number) => {
    setForm(current => ({ ...current, replyDelaySeconds: value }))
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
  const {
    emotes,
    otherChannels,
    loading: emotesLoading,
    error: emotesError,
  } = useChannelEmotes(open)

  const successPreviewParts = useMemo(
    () => tokenizeVars(form.successTemplate, PREVIEW_VALUES),
    [form.successTemplate]
  )
  const duplicatePreviewParts = useMemo(
    () => tokenizeVars(form.duplicateTemplate, PREVIEW_VALUES),
    [form.duplicateTemplate]
  )

  const handleSave = async () => {
    const timezone = form.timezone.trim()
    if (!timezone || !form.successTemplate.trim() || !form.duplicateTemplate.trim()) {
      setValidationError('時區與兩種訊息模板都不可留空。')
      return
    }
    if (
      !Number.isInteger(form.replyDelaySeconds) ||
      form.replyDelaySeconds < 0 ||
      form.replyDelaySeconds > 30
    ) {
      setValidationError('回覆延遲需為 0 到 30 之間的整數秒數。')
      return
    }

    setSaving(true)
    setValidationError(null)
    try {
      const updated = await updateCheckinSettings({
        timezone,
        success_template: form.successTemplate,
        duplicate_template: form.duplicateTemplate,
        reply_delay_seconds: form.replyDelaySeconds,
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
      <SheetContent className="gap-section sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle>Check-in settings</SheetTitle>
          <SheetDescription>
            時區與回覆模板由聊天指令與 Twitch 點數簽到共用；獎勵綁定仍在表格管理。
          </SheetDescription>
        </SheetHeader>

        <div className="grid flex-1 items-start gap-section overflow-y-auto px-page pb-page lg:grid-cols-2">
          <div className="space-y-card">
            {loading ? (
              <div className="space-y-4">
                <Skeleton className="h-16 w-full" />
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
                  <Select
                    value={form.timezone}
                    onValueChange={value => updateForm('timezone', value)}
                  >
                    <SelectTrigger id="checkin-timezone" aria-label="時區" className="w-full">
                      <SelectValue placeholder="選擇時區" />
                    </SelectTrigger>
                    <SelectContent>
                      {timezoneOptions.map(option => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-label text-muted-foreground">決定每日簽到跨日的時間點。</p>
                </section>

                <section
                  className="space-y-2 border-t pt-card"
                  aria-labelledby="checkin-reply-delay-label"
                >
                  <Label id="checkin-reply-delay-label" htmlFor="checkin-reply-delay">
                    回覆延遲（秒）
                  </Label>
                  <Input
                    id="checkin-reply-delay"
                    aria-label="簽到回覆延遲秒數"
                    type="number"
                    min={0}
                    max={30}
                    step={1}
                    value={form.replyDelaySeconds}
                    onChange={event => updateReplyDelay(Number(event.target.value))}
                  />
                  <p className="text-label text-muted-foreground">
                    補償畫面比聊天室晚顯示的秒數；預設 0 秒（不延遲）。
                  </p>
                </section>

                <section className="space-y-3 border-t pt-card">
                  <Tabs defaultValue="success">
                    <TabsList className="grid w-full grid-cols-2">
                      <TabsTrigger value="success">成功訊息</TabsTrigger>
                      <TabsTrigger value="duplicate">已簽到訊息</TabsTrigger>
                    </TabsList>
                    <TabsContent value="success" className="space-y-3">
                      <p className="text-label text-muted-foreground">
                        當今天第一次簽到成功時回覆。
                      </p>
                      <Textarea
                        id="checkin-success-template"
                        aria-label="簽到成功訊息"
                        ref={successInputRef}
                        value={form.successTemplate}
                        maxLength={500}
                        rows={3}
                        className="font-mono text-sub"
                        onChange={event => updateForm('successTemplate', event.target.value)}
                      />
                      <VariableInserter
                        variables={CHECKIN_VARIABLES}
                        onInsert={insertSuccessVariable}
                      />
                      <EmoteInserter
                        emotes={emotes}
                        otherChannels={otherChannels}
                        onInsert={insertSuccessVariable}
                        loading={emotesLoading}
                        error={emotesError}
                      />
                      <TemplatePartsPreview
                        parts={successPreviewParts}
                        limit={TWITCH_MESSAGE_LIMIT}
                        legend={PREVIEW_LEGEND}
                      />
                    </TabsContent>
                    <TabsContent value="duplicate" className="space-y-3">
                      <p className="text-label text-muted-foreground">
                        同一位觀眾在同一天重複簽到時回覆，不會增加累積天數。
                      </p>
                      <Textarea
                        id="checkin-duplicate-template"
                        aria-label="已簽到訊息"
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
                      <EmoteInserter
                        emotes={emotes}
                        otherChannels={otherChannels}
                        onInsert={insertDuplicateVariable}
                        loading={emotesLoading}
                        error={emotesError}
                      />
                      <TemplatePartsPreview
                        parts={duplicatePreviewParts}
                        limit={TWITCH_MESSAGE_LIMIT}
                        legend={PREVIEW_LEGEND}
                      />
                    </TabsContent>
                  </Tabs>
                </section>

                {validationError && (
                  <p className="text-label text-destructive" role="alert">
                    {validationError}
                  </p>
                )}
              </>
            )}
          </div>

          <div className="lg:border-l lg:pl-section">
            <CheckinLeaderboard
              entries={leaderboard}
              loading={leaderboardLoading}
              loadFailed={leaderboardLoadFailed}
              onRetry={() => void loadLeaderboard()}
            />
          </div>
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
