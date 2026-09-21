import { SettingRow } from '@/components/SettingRow'
import {
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@/components/ui'

import { clampValue, MIN_VIEW_COUNT_OPTIONS } from './utils'

export interface RulesDraft {
  maxDurationMinutes: string
  minViewCount: string
  replayCooldownHours: string
  maxPerUser: string
  userCooldownSeconds: string
  maxQueueSize: string
  maxRedemptionDuration: string
  volumePercent: string
}

const GROUP_LABEL = 'text-sub font-medium'
// A trailing lone item in an odd-sized group spans both columns instead of
// dangling in an otherwise-empty second half of the last row.
const GRID =
  'grid grid-cols-1 gap-x-card gap-y-card sm:grid-cols-2 sm:[&>*:last-child:nth-child(odd)]:col-span-2'

// Every right-side control occupies the same fixed width so the input boxes and
// the select triggers line up vertically down the card, whatever the unit.
const CONTROL_WIDTH = 'w-36'

function NumberField({
  value,
  onChange,
  min,
  max,
  placeholder,
  unit,
}: {
  value: string
  onChange: (v: string) => void
  min: number
  max: number
  placeholder: string
  unit: string
}) {
  return (
    <div className={`flex ${CONTROL_WIDTH} shrink-0 items-center justify-end gap-1.5`}>
      <Input
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        onBlur={e => onChange(clampValue(e.target.value, min, max))}
        className="w-16 text-right"
      />
      <span className="w-10 shrink-0 text-sub text-muted-foreground">{unit}</span>
    </div>
  )
}

export function RulesPanel({
  draft,
  onField,
}: {
  draft: RulesDraft
  onField: (key: keyof RulesDraft, value: string) => void
}) {
  return (
    <div className="flex flex-col gap-card">
      <p className={GROUP_LABEL}>所有來源</p>
      <div className={GRID}>
        <SettingRow
          title="影片最長"
          description="Chat、頻道點數、Donate 與手動加入都會套用；0 代表不限"
        >
          <NumberField
            value={draft.maxDurationMinutes}
            onChange={v => onField('maxDurationMinutes', v)}
            min={0}
            max={1440}
            placeholder="0"
            unit="分"
          />
        </SettingRow>
      </div>

      <Separator />

      <p className={GROUP_LABEL}>觀眾加入來源</p>
      <div className={GRID}>
        <SettingRow
          title="至少要有多少觀看數"
          description="套用 Chat、頻道點數與 Donate；手動加入不受限"
        >
          <Select value={draft.minViewCount} onValueChange={v => onField('minViewCount', v)}>
            <SelectTrigger className={CONTROL_WIDTH}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MIN_VIEW_COUNT_OPTIONS.map(opt => (
                <SelectItem key={opt.value} value={String(opt.value)}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingRow>
        <SettingRow
          title="播過多久內不能再點"
          description="套用 Chat、頻道點數與 Donate；0 代表不限"
        >
          <NumberField
            value={draft.replayCooldownHours}
            onChange={v => onField('replayCooldownHours', v)}
            min={0}
            max={168}
            placeholder="0"
            unit="小時"
          />
        </SettingRow>
        <SettingRow title="佇列最多" description="觀眾加入來源共用容量；手動加入可略過">
          <NumberField
            value={draft.maxQueueSize}
            onChange={v => onField('maxQueueSize', v)}
            min={1}
            max={100}
            placeholder="20"
            unit="首"
          />
        </SettingRow>
      </div>

      <Separator />

      <p className={GROUP_LABEL}>可識別觀眾</p>
      <div className={GRID}>
        <SettingRow title="每人同時最多" description="還在排隊的數量，0 代表不限">
          <NumberField
            value={draft.maxPerUser}
            onChange={v => onField('maxPerUser', v)}
            min={0}
            max={20}
            placeholder="0"
            unit="首"
          />
        </SettingRow>
        <SettingRow
          title="兩次點播間隔"
          description="套用 Chat 與頻道點數；Donate 沒有穩定 Twitch 身分"
        >
          <NumberField
            value={draft.userCooldownSeconds}
            onChange={v => onField('userCooldownSeconds', v)}
            min={0}
            max={3600}
            placeholder="0"
            unit="秒"
          />
        </SettingRow>
      </div>
    </div>
  )
}
